# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the API and Next development server; stop both on exit."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
processes: list[subprocess.Popen] = []


def interrupted(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, interrupted)
try:
    for command in (
        [sys.executable, "-m", "app.tasks.worker"],
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.asgi:app",
            "--reload",
            "--reload-dir",
            "backend/app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        ["npm", "--prefix", "frontend", "run", "dev"],
    ):
        processes.append(subprocess.Popen(command, cwd=root, start_new_session=True))
    while all(process.poll() is None for process in processes):
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
