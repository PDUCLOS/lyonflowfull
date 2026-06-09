import os
import socket
import subprocess
import time

import pytest


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


@pytest.fixture(scope="session", autouse=True)
def streamlit_server():
    """Start Streamlit server before E2E tests and kill it after."""
    port = 8502

    # Check if port is already in use
    if is_port_in_use(port):
        yield f"http://localhost:{port}"
        return

    env = os.environ.copy()
    env["STREAMLIT_SERVER_PORT"] = str(port)
    env["STREAMLIT_SERVER_HEADLESS"] = "true"

    import sys

    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard/Accueil.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for the server to be ready
    for _ in range(20):
        if is_port_in_use(port):
            break
        time.sleep(0.5)
    else:
        # Failed to start
        process.terminate()
        outs, errs = process.communicate()
        raise RuntimeError(f"Streamlit failed to start on port {port}.\nStdout: {outs}\nStderr: {errs}")

    yield f"http://localhost:{port}"

    # Teardown
    process.terminate()
    process.wait(timeout=5)
