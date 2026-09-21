"""Offline API/worker fixture, used only by scripts/smoke_capture.py."""

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import uvicorn
from app.config import Settings
from app.db.session import create_db_engine, session_factory
from app.extractors import bilibili, generic, xiaoheihe, xiaohongshu
from app.extractors.base import ExtractionError
from app.extractors.generic import ScopedCookie
from app.extractors.xhs_api import XhsClient
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


def fetch_xiaohongshu(
    url: str, *, cookie: ScopedCookie | None = None, **kwargs: object
) -> tuple[str, str]:
    fixture = (
        "xiaohongshu.html"
        if cookie and cookie.value.get_secret_value() == "web_session=offline-capture"
        else "xiaohongshu-login.html"
    )
    final_url = (
        "https://www.xiaohongshu.com/explore/64abc123?xsec_token=offline"
        if url.startswith("https://xhslink.cn/")
        else url
    )
    return (Path(__file__).parents[1] / "fixtures" / fixture).read_text(), final_url


def xhs_comments(self: XhsClient, note_id: str, token: str, cursor: str) -> dict[str, Any]:
    page = "page2" if cursor == "page2" else "page1"
    path = Path(__file__).parents[1] / "fixtures" / f"xiaohongshu-comments-{page}.json"
    return json.loads(path.read_text())["data"]


def fetch_heybox(url: str, **kwargs: object) -> tuple[str, str]:
    path = Path(__file__).parents[1] / "fixtures" / "xiaoheihe.html"
    return path.read_text(), "https://www.xiaoheihe.cn/app/bbs/link/opaque123"


def heybox_page(
    self: xiaoheihe.HeyboxClient, identifier: str, number: int, limit: int
) -> dict[str, Any]:
    path = Path(__file__).parents[1] / "fixtures" / f"xiaoheihe-page{number}.json"
    return json.loads(path.read_text())["result"]


def xhs_login(self: XhsClient) -> bool:
    return self.cookie.value.get_secret_value() == "web_session=offline-capture"


def heybox_login(self: xiaoheihe.HeyboxClient) -> bool:
    if self.cookie.value.get_secret_value() == "session=offline-restricted":
        raise ExtractionError("小黑盒限制访问，请在浏览器完成验证后重试", False)
    return True


def fetch_bilibili(url: str, **kwargs: object) -> tuple[str, str]:
    return (Path(__file__).parents[1] / "fixtures" / "bilibili.html").read_text(), url


def bili_json(url: str, **kwargs: object) -> dict[str, Any]:
    parts = urlsplit(url)
    if parts.path == "/x/player/wbi/v2":
        name = "bilibili-player.json"
    elif parts.path == "/x/v2/reply":
        name = f"bilibili-comments{parse_qs(parts.query)['pn'][0]}.json"
    elif parts.path.startswith("/bfs/subtitle/"):
        name = "bilibili-captions.json"
    else:
        raise AssertionError("Unexpected offline video request")
    return json.loads((Path(__file__).parents[1] / "fixtures" / name).read_text())


class OfflineModel:
    def complete(self, **kwargs: Any) -> str:
        comments = json.loads(kwargs["messages"][1]["content"])["comments"]
        if kwargs["model"] == "offline-no-scores":
            comments = []
        return json.dumps(
            {
                "summary_markdown": "## 给未来留一份笔记\n保留来源、压缩观点，并定期回顾。",
                "key_points": ["保存来源与完整正文", "定期回顾并付诸行动"],
                "suggested_tags": ["知识管理"],
                "comment_scores": [
                    {
                        "index": row["index"],
                        "score": 0.9 if row["index"] == 0 else 0.6,
                        "reason": "提供了可操作的补充建议",
                    }
                    for row in comments
                ],
            }
        )


if __name__ == "__main__":
    settings = Settings(_env_file=None)
    if sys.argv[1] == "worker":
        generic.fetch_html = fetch
        xiaohongshu.fetch_html = fetch_xiaohongshu
        XhsClient.comments = xhs_comments
        XhsClient.check_login = xhs_login
        xiaoheihe.fetch_html = fetch_heybox
        xiaoheihe.HeyboxClient.page = heybox_page
        xiaoheihe.HeyboxClient.check_login = heybox_login
        bilibili.fetch_html = fetch_bilibili
        bilibili.fetch_json = bili_json
        engine = create_db_engine(settings)
        queue = CaptureQueue(session_factory(engine), settings)
        queue.pipeline.llm = OfflineModel()
        queue.recover()
        Consumer(queue.huey, workers=1).run()
    else:
        uvicorn.run(
            create_app(settings), host="127.0.0.1", port=int(os.environ["CLIPO_SMOKE_PORT"])
        )
