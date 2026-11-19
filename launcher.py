from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn


BASE_DIR = Path(__file__).resolve().parent


def configure_portable_env() -> None:
    """Ensure bundled FFmpeg and Deno binaries are first on PATH and app root is importable."""
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    runtime_ffmpeg = BASE_DIR / "runtime" / "ffmpeg"
    runtime_bin = BASE_DIR / "runtime" / "bin"

    extra_paths = [str(p) for p in (runtime_ffmpeg, runtime_bin) if p.exists()]
    if extra_paths:
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(extra_paths + ([current_path] if current_path else []))


def find_free_port(start_port: int = 8000, max_attempts: int = 21) -> int:
    """Find an available localhost TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start_port}-{start_port + max_attempts - 1}.")


def open_browser_when_ready(url: str, timeout: float = 15.0) -> None:
    """Poll /api/health until the server responds, then open the default browser."""
    health_url = f"{url}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                if resp.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.25)


def main() -> None:
    configure_portable_env()

    raw_port = os.environ.get("PULSEDL_PORT", "8000")
    try:
        start_port = int(raw_port)
    except ValueError:
        start_port = 8000

    port = find_free_port(start_port=start_port, max_attempts=21)
    url = f"http://127.0.0.1:{port}"
    downloads_dir = BASE_DIR / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  PulseDL Portable - MP3 Studio & Universal Video Downloader")
    print("=" * 60)
    print(f"  Web UI:    {url}")
    print(f"  Downloads: {downloads_dir}")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)

    no_browser = "--no-browser" in sys.argv or os.environ.get("PULSEDL_NO_BROWSER") == "1"
    if not no_browser:
        threading.Thread(
            target=open_browser_when_ready,
            args=(url,),
            daemon=True,
        ).start()

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
