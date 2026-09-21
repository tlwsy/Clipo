"""Read-only XHS web API calls; credentials and signatures never leave the API host."""

import re
from typing import Any

from pydantic import SecretStr
from xhshow import Xhshow

from app.extractors.base import ExtractionError
from app.extractors.generic import PlatformRequests, ScopedCookie, fetch_json

API_HOSTS = frozenset({"edith.xiaohongshu.com"})
API_BASE = "https://edith.xiaohongshu.com"
LOGIN_ERROR = "小红书登录态失效，请在设置中更新 Cookie 后重试"


def check_status(status: int) -> None:
    if status == 401:
        raise ExtractionError(LOGIN_ERROR, False)
    if status in (403, 406, 461, 471):
        raise ExtractionError("小红书限制访问，请在浏览器完成验证并更新 Cookie 后重试", False)
    if status == 429:
        raise ExtractionError("小红书请求过于频繁，请稍后重试")


class XhsClient:
    def __init__(self, cookie: SecretStr, requests: PlatformRequests | None = None) -> None:
        self.cookie = ScopedCookie(cookie, API_HOSTS)
        self.requests = requests or PlatformRequests()
        self.signer = Xhshow()

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if path not in ("/api/sns/web/v2/comment/page", "/api/sns/web/v1/user/selfinfo"):
            raise ValueError("Unsupported XHS endpoint")
        # The signer's query builder only escapes '='. Reject query delimiters rather than
        # permit a page-provided token/cursor to inject other parameters into signed requests.
        if any(
            len(value) > 2048 or not re.fullmatch(r"[\w.,~+/%=-]*", value, re.ASCII)
            for value in params.values()
        ):
            raise ExtractionError("小红书分页参数无法识别，请重新复制完整帖子链接", False)
        try:
            headers = self.signer.sign_headers_get(
                uri=path,
                cookies=self.cookie.value.get_secret_value(),
                params=params,
            )
        except Exception:
            raise ExtractionError(
                "小红书 Cookie 缺少有效的 a1，请重新复制完整 Cookie", False
            ) from None
        response = fetch_json(
            self.signer.build_url(API_BASE + path, params),
            allowed_hosts=API_HOSTS,
            cookie=self.cookie,
            headers={
                **headers,
                "Origin": "https://www.xiaohongshu.com",
                "Referer": "https://www.xiaohongshu.com/",
            },
            check_status=check_status,
            requests=self.requests,
        )
        if response.get("code") in (-100, -101, -102):
            raise ExtractionError(LOGIN_ERROR, False)
        if response.get("code") in (300011, 300012):
            raise ExtractionError("小红书限制访问，请在浏览器完成验证后重试", False)
        if response.get("success") is not True or not isinstance(response.get("data"), dict):
            raise ExtractionError("小红书接口未返回可用数据，请检查 Cookie 或反馈适配问题", False)
        return response["data"]

    def comments(self, note_id: str, token: str, cursor: str) -> dict[str, Any]:
        return self.get(
            "/api/sns/web/v2/comment/page",
            {
                "note_id": note_id,
                "cursor": cursor,
                "top_comment_id": "",
                "image_formats": "jpg,webp,avif",
                "xsec_token": token,
            },
        )

    def check_login(self) -> bool:
        data = self.get("/api/sns/web/v1/user/selfinfo", {})
        result = data.get("result")
        if isinstance(result, dict) and type(result.get("success")) is bool:
            return result["success"]
        raise ExtractionError("小红书未返回明确的登录状态，请稍后重试", False)
