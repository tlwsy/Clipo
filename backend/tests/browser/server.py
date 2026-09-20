"""Offline API/worker fixture, used only by scripts/smoke_capture.py."""

import json
import os
import sys
from pathlib import Path

import uvicorn
from app.config import Settings
from app.db.session import create_db_engine, session_factory
from app.extractors import generic
from app.extractors.base import ExtractionError
from app.main import create_app
from app.tasks.capture import CaptureQueue
from huey.consumer import Consumer

html = (Path(__file__).parents[1] / "fixtures" / "article.html").read_text()
attempts: dict[str, int] = {}


def fetch(url: str) -> tuple[str, str]:
    attempts[url] = attempts.get(url, 0) + 1
    if "/retry" in url and attempts[url] == 1:
        raise ExtractionError("测试网页暂时限制访问，请点击重新保存", False)
    return html, url


class OfflineModel:
    def complete(self, **kwargs) -> str:
        return json.dumps(
            {
                "summary_markdown": "## 给未来留一份笔记\n保留来源、压缩观点，并定期回顾。",
                "key_points": ["保存来源与完整正文", "定期回顾并付诸行动"],
                "suggested_tags": ["知识管理"],
            }
        )


if __name__ == "__main__":
    settings = Settings(_env_file=None)
    if sys.argv[1] == "worker":
        generic.fetch_html = fetch
        engine = create_db_engine(settings)
        queue = CaptureQueue(session_factory(engine), settings)
        queue.pipeline.llm = OfflineModel()
        queue.recover()
        Consumer(queue.huey, workers=1).run()
    else:
        uvicorn.run(
            create_app(settings), host="127.0.0.1", port=int(os.environ["CLIPO_SMOKE_PORT"])
        )
