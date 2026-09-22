# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bound streaming capture requests before JSON parsing (including chunked transfer)."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.payload import CHUNK_BYTES, DIRECT_BYTES


class CaptureBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/v1/captures"):
            await self.app(scope, receive, send)
            return
        limit = CHUNK_BYTES if "/chunks/" in path else DIRECT_BYTES
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            data.extend(message.get("body", b""))
            if len(data) > limit:
                response = JSONResponse(
                    {
                        "error": {
                            "code": "body_too_large",
                            "message": "内容超过单次请求上限，请使用分块上传或缩小页面内容",
                            "detail": {},
                        }
                    },
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
