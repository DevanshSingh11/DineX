"""Run the optional DOM integration check against an isolated loopback DineX server."""

import json
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dinex.app import create_app
from dinex.config import Config
from dinex.db import add, make_engine, migrate, unit
from dinex.models import PlatformUser
from dinex.security import password_hash


def main():
    node = shutil.which("node")
    if not node or not (ROOT / "checks/ui/node_modules/jsdom").is_dir():
        sys.exit(
            "Install Node.js 22+ and run npm ci --prefix checks/ui for this optional UI check."
        )
    with tempfile.TemporaryDirectory(prefix="dinex-dom-") as temporary:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
            cfg = Config(
                Path(temporary) / "journey.sqlite3", secrets.token_urlsafe(48), origin
            )
            db_engine = make_engine(cfg.database)
            migrate(db_engine)
            password = secrets.token_urlsafe(26)
            with unit(db_engine, True) as db:
                add(
                    db,
                    PlatformUser,
                    name="Test operator",
                    email="operator@example.test",
                    password_hash=password_hash(password),
                )
            db_engine.dispose()
            server = uvicorn.Server(
                uvicorn.Config(
                    create_app(cfg),
                    host="127.0.0.1",
                    log_level="warning",
                    access_log=False,
                )
            )
            worker = threading.Thread(
                target=server.run, kwargs={"sockets": [listener]}, daemon=True
            )
            worker.start()
            try:
                for _ in range(200):
                    if server.started:
                        break
                    time.sleep(0.025)
                if not server.started:
                    raise RuntimeError("Test server did not start.")
                result = subprocess.run(
                    [node, "journey.mjs"],
                    cwd=ROOT / "checks/ui",
                    input=json.dumps({"origin": origin, "password": password}),
                    text=True,
                    timeout=120,
                )
                if result.returncode:
                    sys.exit(result.returncode)
            finally:
                server.should_exit = True
                worker.join(10)


if __name__ == "__main__":
    main()
