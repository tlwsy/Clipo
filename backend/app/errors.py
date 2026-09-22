# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any


class ClipoError(Exception):
    def __init__(
        self, status: int, code: str, message: str, detail: dict[str, Any] | None = None
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


def validation_message(field: str, error_type: str) -> str:
    """Explain expected values without echoing user inputs or validator exceptions."""
    messages = {
        "body.username": "用户名需为 3–64 个字符，只能包含文字、数字、下划线和短横线",
        "body.email": "请输入有效的邮箱地址，例如 you@example.com",
        "body.password": "密码长度不符合要求，请按页面提示填写",
        "body.llm.base_url": "AI 服务地址需为完整的 HTTP(S) 地址，例如 https://api.deepseek.com/v1",
        "body.llm.model": "模型名称需为 1–100 个字符，例如 qwen-plus",
        "body.llm.api_key": "API Key 最多为 4096 个字符，也可以留空稍后配置",
        "body.llm.max_comments": "候选评论上限需为 1–100 之间的整数",
        "body.capture.max_comments": "评论采集上限需为 0–100 之间的整数，0 表示不采集评论",
        "body.llm.comment_score_threshold": "高价值评论阈值需为 0–1 之间的数字",
        "body.url": "请提供公开网页的 HTTP(S) 链接，不支持内网地址、账号密码或非标准端口",
        "body.payload": "页面内容不符合直传格式，请更新扩展后重试",
    }
    if error_type == "json_invalid":
        return "请求格式有误，请发送有效的 JSON 内容"
    if field.startswith("body.platform_cookies"):
        return (
            "平台仅支持小红书和小黑盒；请粘贴 Cookie 请求头的值（name=value; name2=value2），"
            "不要包含 Cookie: 前缀、换行或非 ASCII 字符，最多 16384 个字符"
        )
    return messages.get(field, "填写内容有误，请检查对应字段的格式和长度")
