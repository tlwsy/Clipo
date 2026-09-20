"""Supervise the API and worker so either failure terminates the container."""

import os
import signal
import subprocess
import sys


def main():
    processes = []

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    exit_code = 0
    try:
        for command in (
            [sys.executable, "-m", "app.tasks.worker"],
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.asgi:app",
                "--host",
                os.environ.get("CLIPO_BIND_HOST", "127.0.0.1"),
                "--port",
                "8000",
            ],
        ):
            processes.append(subprocess.Popen(command, start_new_session=True))
        import time

        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        exit_code = 1
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
