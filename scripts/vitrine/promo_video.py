"""Vidéo de présentation LyonFlow (1080p), adaptée du générateur de LLMRAGlangchain.

Chaîne : scènes HTML -> PNG 1920x1080 (Edge headless) -> narration française
(voix Windows Hortense, System.Speech) -> clips ffmpeg (zoom lent + fondus)
-> concaténation + nappe sonore synthétisée (aucun fichier sous licence).

Toutes les valeurs citées viennent de docs/measures/ (mesurées le 27/10/2026)
ou du code ; les captures sont celles de docs/screenshots et docs/diagrams.

Usage (Windows) :  python scripts/vitrine/promo_video.py
Sortie : docs/video/lyonflow-promo.mp4 (+ affiche docs/video/poster.png)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OUT = DOCS / "video"
WORK = Path(tempfile.gettempdir()) / "lyonflow_promo"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "ffprobe"
FPS = 30
PAD_S = 0.8  # respiration après chaque phrase

CSS = """
:root { --bg:#0d1a14; --ink:#e9f2ec; --muted:#a8bcb0; --accent:#6fd39a; --warn:#f0b65a; }
* { box-sizing:border-box; margin:0; }
html,body { width:1920px; height:1080px; overflow:hidden; background:var(--bg); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,sans-serif; }
.stage { width:1920px; height:1080px; padding:110px 140px; display:grid; align-content:center; gap:34px;
  background: radial-gradient(1200px 700px at 85% 15%, #1b3a2b 0%, transparent 60%), var(--bg); }
.eyebrow { font:500 26px "IBM Plex Mono",monospace; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
h1 { font:700 100px/1.03 "IBM Plex Sans Condensed",sans-serif; letter-spacing:-.015em; max-width:1550px; }
h1 em { font-style:normal; color:var(--accent); }
p.sub { font-size:38px; line-height:1.45; color:var(--muted); max-width:1500px; }
ul { list-style:none; padding:0; display:grid; gap:24px; }
li { font-size:42px; line-height:1.3; padding-left:56px; position:relative; }
li::before { content:""; position:absolute; left:0; top:22px; width:28px; height:4px; background:var(--accent); }
li.no::before { background:var(--warn); }
.kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:2px; background:rgba(255,255,255,.14); border-radius:10px; overflow:hidden; }
.kpi { background:var(--bg); padding:40px 30px; display:grid; gap:10px; }
.kpi b { font:700 88px "IBM Plex Sans Condensed",sans-serif; color:#fff; }
.kpi span { font-size:27px; color:var(--muted); line-height:1.3; }
.shotstage { width:1920px; height:1080px; display:grid; grid-template-rows:1fr auto; background:var(--bg); }
.frame { display:grid; place-items:center; padding:44px 60px 22px; overflow:hidden; }
.frame img { max-width:100%; max-height:860px; border-radius:12px; box-shadow:0 30px 80px rgba(0,0,0,.5); border:1px solid rgba(255,255,255,.14); }
.frame.light img { background:#fff; padding:14px; }
.band { padding:24px 60px 40px; display:flex; gap:30px; align-items:baseline; }
.band .tag { font:500 24px "IBM Plex Mono",monospace; color:var(--accent); letter-spacing:.12em; text-transform:uppercase; white-space:nowrap; }
.band .cap { font:500 40px/1.3 "IBM Plex Sans",sans-serif; }
.url { font:500 40px "IBM Plex Mono",monospace; color:var(--accent); }
"""
FONTS = (
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:'
    'wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap">'
)


def page(body: str) -> str:
    return f'<!doctype html><html lang="fr"><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>{body}</body></html>'


def card(eyebrow: str, title: str, sub: str = "", extra: str = "") -> str:
    sub_html = f'<p class="sub">{sub}</p>' if sub else ""
    return page(f'<div class="stage"><span class="eyebrow">{eyebrow}</span><h1>{title}</h1>{sub_html}{extra}</div>')


def shot(image: str, tag: str, caption: str, light: bool = False) -> str:
    src = (DOCS / image).as_uri()
    cls = "frame light" if light else "frame"
    return page(
        f'<div class="shotstage"><div class="{cls}"><img src="{src}"></div>'
        f'<div class="band"><span class="tag">{escape(tag)}</span><span class="cap">{caption}</span></div></div>'
    )


KPIS = (
    '<div class="kpis">'
    + "".join(
        f'<div class="kpi"><b>{v}</b><span>{t}</span></div>'
        for v, t in [
            ("27", "DAGs Airflow inventoriés dans le code"),
            ("650", "tests pytest verts, 0 échec"),
            ("5,4 ms", "prédiction médiane, 3 quantiles (jeu synthétique)"),
            ("0,24", "PSI pour un décalage d'un demi écart-type"),
        ]
    )
    + "</div>"
)

# (identifiant, html, narration, zoom final)
SCENES = [
    (
        "01-titre",
        card(
            "LyonFlow · MLOps · Métropole de Lyon",
            "La mobilité lyonnaise <em>prédite à une heure</em>.",
            "Trafic routier, bus TCL, Vélo'v : neuf flux ouverts croisés dans une seule plateforme.",
        ),
        "La Métropole de Lyon publie des dizaines de flux ouverts. LyonFlow les croise pour prédire le trafic à une heure.",
        1.04,
    ),
    (
        "02-besoin",
        card(
            "Le besoin",
            "Trois publics, trois décisions.",
            extra="<ul><li>L'usager : quel mode de transport, maintenant ?</li>"
            "<li>L'opérateur TCL : où le réseau décroche-t-il ?</li>"
            "<li>L'élu : faut-il une voie de bus dédiée ?</li></ul>",
        ),
        "Trois publics. L'usager choisit son mode de transport. L'opérateur pilote son réseau. "
        "L'élu arbitre un investissement, comme une voie de bus dédiée.",
        1.03,
    ),
    (
        "03-archi",
        shot(
            "diagrams/architecture-p1.png",
            "Architecture",
            "Bronze immuable, Silver nettoyé, Gold prêt pour le ML.",
            light=True,
        ),
        "Airflow collecte les flux toutes les cinq minutes. Les données sont raffinées en trois couches dans PostgreSQL, "
        "puis alimentent deux modèles XGBoost et un calcul d'itinéraire pgRouting.",
        1.10,
    ),
    (
        "04-dashboard",
        shot("screenshots/streamlit-accueil.png", "Dashboard réel", "Accueil Streamlit : un parcours par persona."),
        "Le tableau de bord Streamlit propose une vue par public. Ici, l'application lancée sur notre machine de test.",
        1.06,
    ),
    (
        "05-mlops",
        shot(
            "diagrams/architecture-p2.png",
            "MLOps",
            "Entraînement quotidien, registre MLflow, inférence toutes les 15 min, dérive PSI.",
            light=True,
        ),
        "Le modèle est réentraîné chaque nuit, enregistré dans MLflow, et prédit toutes les quinze minutes. "
        "Chaque matin, un rapport de dérive compare ses erreurs aux vitesses mesurées par TomTom.",
        1.10,
    ),
    (
        "06-mesures",
        card("Mesuré le 27 octobre 2026", "Les chiffres vérifiés ici.", extra=KPIS),
        "Ce que nous avons vérifié. Vingt-sept DAGs dans le code. Six cent cinquante tests verts. "
        "Une prédiction en cinq millisecondes et demie. Et un indicateur de dérive qui réagit dès un demi écart-type.",
        1.03,
    ),
    (
        "07-correction",
        shot(
            "screenshots/streamlit-statut-service.png",
            "Corrigé",
            "Base injoignable : des voyants « Indéterminé » au lieu d'une trace Python.",
        ),
        "En testant sans base de données, la page Statut du service affichait une erreur brute. "
        "Elle est corrigée : chaque voyant passe en indéterminé.",
        1.06,
    ),
    (
        "08-k8s",
        shot(
            "diagrams/architecture-p3.png",
            "Kubernetes",
            "Cible réveillée et rendue par kubectl kustomize, pas encore déployée.",
            light=True,
        ),
        "La cible Kubernetes, en sommeil sur une branche, est réalignée sur le code actuel et validée par kustomize. "
        "Elle n'est pas encore déployée.",
        1.10,
    ),
    (
        "09-limites",
        card(
            "Honnêteté",
            "Ce qui n'a pas été vérifié ici.",
            extra='<ul><li class="no">La production sur serveur et ses données réelles</li>'
            '<li class="no">La précision des modèles en conditions réelles</li>'
            '<li class="no">Un déploiement Kubernetes effectif</li></ul>',
        ),
        "Ce que nous n'avons pas pu vérifier sur cette machine : le serveur de production, ses données, "
        "et la précision réelle des modèles. Ces points restent à confirmer.",
        1.03,
    ),
    (
        "10-fin",
        card(
            "LyonFlow",
            "Le code, la démarche et les mesures sont publics.",
            extra='<p class="url">github.com/PDUCLOS/lyonflowfull</p>'
            '<p class="sub">Patrice Duclos · Architecte IA (RNCP 38777)</p>',
        ),
        "LyonFlow. Le code, la démarche et les mesures sont sur GitHub.",
        1.04,
    ),
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def render_png(html: str, png: Path) -> None:
    src = png.with_suffix(".html")
    src.write_text(html, encoding="utf-8")
    run(
        [
            EDGE,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--user-data-dir={WORK / 'edge-profile'}",
            "--allow-file-access-from-files",
            "--window-size=1920,1080",
            "--virtual-time-budget=4000",
            f"--screenshot={png}",
            src.as_uri(),
        ]
    )


def narrate(text: str, wav: Path) -> None:
    txt = wav.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.SelectVoice('Microsoft Hortense Desktop'); $s.Rate = 1;"
        f"$s.SetOutputToWaveFile('{wav}');"
        f"$s.Speak([IO.File]::ReadAllText('{txt}', [Text.Encoding]::UTF8)); $s.Dispose()"
    )
    run(["powershell", "-NoProfile", "-Command", ps])


def duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def encoder() -> list[str]:
    probe = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "h264_nvenc" in probe:
        return ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "26", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "24"]


def clip(png: Path, wav: Path, zoom: float, mp4: Path) -> float:
    dur = duration(wav) + PAD_S
    frames = int(dur * FPS)
    step = (zoom - 1.0) / frames
    vf = (
        f"[0:v]scale=3840:2160,zoompan=z='min(1+{step:.6f}*on,{zoom})':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps={FPS},"
        f"fade=t=in:st=0:d=0.45,fade=t=out:st={dur - 0.45:.2f}:d=0.45,format=yuv420p[v];"
        f"[1:a]adelay=350|350,apad,atrim=0:{dur:.2f},aformat=sample_rates=48000:channel_layouts=stereo[a]"
    )
    run(
        [
            FFMPEG, "-y", "-loop", "1", "-i", str(png), "-i", str(wav), "-filter_complex", vf,
            "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", *encoder(), "-c:a", "aac", "-b:a", "160k", str(mp4),
        ]
    )  # fmt: skip
    return dur


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    clips, total = [], 0.0
    for name, html, text, zoom in SCENES:
        png, wav, mp4 = WORK / f"{name}.png", WORK / f"{name}.wav", WORK / f"{name}.mp4"
        render_png(html, png)
        narrate(text, wav)
        total += clip(png, wav, zoom, mp4)
        clips.append(mp4)
        print(f"  {name}: {total:5.1f} s")

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    joined = WORK / "joined.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])

    # Nappe sonore synthétisée (accord de quinte, battement lent) mixée sous la voix.
    pad = (
        f"aevalsrc='0.05*sin(2*PI*110*t)*(0.6+0.4*sin(2*PI*0.08*t))+0.035*sin(2*PI*164.81*t)"
        f"+0.03*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*0.05*t+1))+0.02*sin(2*PI*329.63*t)':"
        f"s=48000:d={total:.2f},afade=t=in:d=2,afade=t=out:st={total - 3:.2f}:d=3,"
        f"lowpass=f=900,aformat=channel_layouts=stereo,volume=0.55[pad]"
    )
    final = OUT / "lyonflow-promo.mp4"
    run(
        [
            FFMPEG, "-y", "-i", str(joined), "-filter_complex",
            f"{pad};[0:a][pad]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,loudnorm=I=-16:TP=-1.5[a]",
            # Ré-encodage final x264 « stillimage » : < 15 Mo pour GitHub Pages.
            "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "27",
            "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(final),
        ]
    )  # fmt: skip
    shutil.copy(WORK / "01-titre.png", OUT / "poster.png")
    print(f"Vidéo : {final} ({total:.1f} s, {final.stat().st_size / 1e6:.1f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
