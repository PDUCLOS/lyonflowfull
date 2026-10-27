"""Capture d'écran via Edge headless + DevTools Protocol (attente réelle).

Nécessaire pour Streamlit (websocket) : --screenshot ne laisse pas l'app rendre.
Usage : python scripts/vitrine/cdp_shot.py URL sortie.png [largeur hauteur attente_s] [js]
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 48790


async def shot(url: str, out: str, w: int, h: int, wait: float, js: str | None) -> None:
    prof = tempfile.mkdtemp(prefix="cdp_")
    proc = subprocess.Popen(
        [
            EDGE,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={prof}",
            f"--window-size={w},{h}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except OSError:
                time.sleep(0.2)
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            n = 0

            async def call(method, **params):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == n:
                        return msg.get("result", {})

            await call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
            await call("Page.navigate", url=url)
            await asyncio.sleep(wait)
            if js:
                await call("Runtime.evaluate", expression=js, awaitPromise=True)
                await asyncio.sleep(3)
            res = await call("Page.captureScreenshot", format="png")
            with open(out, "wb") as f:
                f.write(base64.b64decode(res["data"]))
    finally:
        proc.terminate()


if __name__ == "__main__":
    a = sys.argv
    asyncio.run(
        shot(
            a[1],
            a[2],
            int(a[3]) if len(a) > 3 else 1440,
            int(a[4]) if len(a) > 4 else 900,
            float(a[5]) if len(a) > 5 else 12,
            a[6] if len(a) > 6 else None,
        )
    )
    print("ok", a[2])
