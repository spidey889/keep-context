"""Optional Cloudflare quick tunnel with bounded startup and automatic cleanup."""

import queue
import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager

from .credentials import SetupError


@contextmanager
def open_tunnel(port: int):
    binary = shutil.which("cloudflared")
    if not binary:
        raise SetupError(
            "Install cloudflared first (Windows: winget install -e --id "
            "Cloudflare.cloudflared), or use serve --public-url with your HTTPS proxy."
        )
    process = subprocess.Popen(
        [
            binary,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{port}",
            "--no-autoupdate",
            "--protocol",
            "http2",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    urls = queue.Queue(maxsize=1)
    ready = threading.Event()
    started = time.monotonic()

    def read_output():
        for line in process.stdout:
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if match and urls.empty():
                urls.put(match.group(0))
            if "Registered tunnel connection" in line:
                ready.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        try:
            url = urls.get(timeout=45)
        except queue.Empty:
            raise SetupError(
                "Cloudflare tunnel did not start within 45 seconds. Check network "
                "access or use a stable HTTPS proxy with --public-url."
            ) from None
        if process.poll() is not None:
            raise SetupError("Cloudflare tunnel exited during startup. Retry or use --public-url.")
        if not ready.wait(timeout=max(0, 45 - (time.monotonic() - started))):
            raise SetupError(
                "Cloudflare allocated a URL but could not connect the tunnel. "
                "Check outbound network access or use a stable HTTPS proxy."
            )
        yield url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        reader.join(timeout=1)
        process.stdout.close()
