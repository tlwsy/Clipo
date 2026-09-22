# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run one durable SQL-backed capture consumer alongside the API."""

from huey.consumer import Consumer

from app.config import get_settings
from app.db.session import create_db_engine, session_factory
from app.tasks.capture import CaptureQueue


def main():
    import logging

    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    # HTTP client logs must never print model endpoints or credentials.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    engine = create_db_engine(settings)
    queue = CaptureQueue(session_factory(engine), settings)
    queue.recover()
    try:
        Consumer(queue.huey, workers=2, worker_type="thread").run()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
