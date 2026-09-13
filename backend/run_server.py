import sys
import os
import socket

try:
    sys.stdin = open(os.devnull, "r")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
CODE_DIR = os.path.join(BASE_DIR, "code")
SITE_PACKAGES = os.path.join(BASE_DIR, ".venv", "Lib", "site-packages")
for p in (SITE_PACKAGES, BACKEND_DIR, CODE_DIR, BASE_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import uvicorn
from backend.main import app

def find_available_port(ports=[8000, 8080, 8001, 8081, 5000]) -> int:
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return 8000

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "0")) or find_available_port()
    print(f"Starting server on http://127.0.0.1:{port} ...")
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    server.run()
