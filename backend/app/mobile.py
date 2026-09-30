"""Entry point for the Android app (docs/07-mobile.md "Android shell").

The Kotlin side calls `start()` once per process with the app's private data and resources
folders; it runs the same FastAPI app as the PC, in the phone role, on a free 127.0.0.1 port in a
background thread, and returns the port for the WebView. Calling it again returns the same port.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import urllib.request

logger = logging.getLogger("app.mobile")

_port: int | None = None
_lock = threading.Lock()
HEALTH_TIMEOUT_S = 60.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def start(data_dir: str, resource_dir: str) -> int:
    global _port
    with _lock:
        if _port is not None and _healthy(_port):
            return _port

        # Settings are read when app.config is first imported, so set these before any app import.
        os.environ["NW_ROLE"] = "phone"
        os.environ["NW_DATA_DIR"] = data_dir
        os.environ["NW_RESOURCE_DIR"] = resource_dir
        os.environ["NW_ENV"] = "production"

        import uvicorn

        from app.main import app

        port = _free_port()
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_config=None,
            # Pure-Python choices: the compiled uvloop/httptools/websockets aren't shipped.
            loop="asyncio",
            http="h11",
            ws="none",
        )
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, name="waymark-server", daemon=True).start()

        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        while time.monotonic() < deadline:
            if _healthy(port):
                _port = port
                logger.info("Waymark server up on 127.0.0.1:%d", port)
                return port
            time.sleep(0.2)
        raise RuntimeError("Waymark's server didn't start; see the log in the app's data folder")
