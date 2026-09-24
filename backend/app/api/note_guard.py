# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Limit anonymous work and bound note action bodies before JSON parsing."""

import re

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import ClipoError
from app.security.note_limits import NoteRateLimiter

NOTE_BODY_BYTES = 4096
PROTECTED = re.compile(
    r"^/api/v1/(?:public/notes/read|notes/[^/]+/(?:summarize|shares)|summary-jobs/[^/]+/retry)/?$"
)


class NoteAccessGuard:
    def __init__(self, app: ASGIApp, limiter: NoteRateLimiter) -> None:
        self.app, self.limiter = app, limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or not PROTECTED.fullmatch(path)
        ):
            await self.app(scope, receive, send)
            return

        async def reject(status: int, code: str, message: str, detail: dict | None = None) -> None:
            headers = {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Robots-Tag": "noindex, nofollow, noarchive",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
            }
            if status == 429 and detail:
                headers["Retry-After"] = str(detail["retry_after"])
            await JSONResponse(
                {"error": {"code": code, "message": message, "detail": detail or {}}},
                status_code=status,
                headers=headers,
            )(scope, receive, send)

        if path.rstrip("/") == "/api/v1/public/notes/read":
            address = (scope.get("client") or ("unknown", 0))[0]
            try:
                # Do not parse X-Forwarded-For here; only the server's trusted peer is used.
                await run_in_threadpool(self.limiter.public_read, address)
            except ClipoError as exc:
                await reject(exc.status, exc.code, exc.message, exc.detail)
                return
            except Exception:
                await reject(503, "database_unavailable", "访问检查暂不可用，请稍后重试")
                return
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(data) + len(chunk) > NOTE_BODY_BYTES:
                await reject(413, "body_too_large", "请求内容过大，请刷新页面后重试")
                return
            data.extend(chunk)
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
