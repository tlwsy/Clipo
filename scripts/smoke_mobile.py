# SPDX-License-Identifier: AGPL-3.0-or-later
"""以临时真实 API 验证 Kotlin 客户端；不读取部署密钥，不请求真实采集站点或模型。"""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from alembic import command
from alembic.config import Config
from app.config import BACKEND_ROOT, Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gradle", default=str(ROOT / "mobile/gradlew"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="clipo-mobile-api-") as temporary:
        folder = Path(temporary)
        settings = Settings(
            _env_file=None,
            secret_key=secrets.token_hex(32),
            database_url=f"sqlite:///{folder / 'test.db'}",
            queue_path=folder / "queue.db",
            backup_path=folder / "backups",
            static_path=folder / "static",
        )
        app = create_app(settings)
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        with app.state.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            assert server.started, "临时移动端 API 启动失败"
            with httpx.Client(base_url=base + "/api/v1", trust_env=False) as client:
                response = client.post(
                    "/setup",
                    json={
                        "username": "mobile-test",
                        "email": "mobile@example.com",
                        "password": "mobile-test-password",
                    },
                )
                response.raise_for_status()
                session = response.json()
                client.headers["Authorization"] = "Bearer " + session["access_token"]
                job = client.post(
                    "/captures",
                    json={
                        "url": "https://example.com/mobile",
                        "payload": {
                            "title": "Mobile acceptance",
                            "text": "中文😀内容\n\nOffline reading.",
                        },
                    },
                )
                job.raise_for_status()
                app.state.capture_queue.pipeline.run(session["user"]["id"], job.json()["job_id"])
                result = client.get("/jobs/" + job.json()["job_id"])
                result.raise_for_status()
                assert result.json()["status"] == "success"
                note_id = result.json()["note_id"]
                annotation = client.post(
                    f"/notes/{note_id}/annotations",
                    json={
                        "block_index": 0,
                        "start_offset": 0,
                        "end_offset": 4,
                        "selected_text": "中文😀",
                        "highlight_color": "yellow",
                    },
                )
                annotation.raise_for_status()
            env = {key: value for key, value in os.environ.items() if not key.startswith("CLIPO_")}
            env["CLIPO_MOBILE_SMOKE_URL"] = base
            subprocess.run(
                [
                    args.gradle,
                    "-p",
                    str(ROOT / "mobile"),
                    ":shared:backendSmoke",
                    "--console=plain",
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
            app.state.engine.dispose()


if __name__ == "__main__":
    main()
