import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app import __version__
from app.api.body_limit import CaptureBodyLimit
from app.api.v1.routes import router
from app.config import Settings, get_settings
from app.db.session import create_db_engine, session_factory
from app.errors import ClipoError, validation_message
from app.services.search import SearchBackend
from app.tasks.capture import CaptureQueue

logger = logging.getLogger("clipo")


def error_response(
    status: int, code: str, message: str, detail: dict | None = None
) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(
        {"error": {"code": code, "message": message, "detail": detail or {}}},
        status_code=status,
        headers=headers,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.search = SearchBackend.detect(engine)
        logger.info("Clipo %s started", __version__)
        yield
        engine.dispose()

    app = FastAPI(title="Clipo API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory(engine)
    app.state.capture_queue = CaptureQueue(app.state.session_factory, settings)

    @app.exception_handler(ClipoError)
    async def handle_clipo_error(request: Request, exc: ClipoError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Never echo validation inputs: they may contain passwords or API keys.
        fields = [
            {
                "field": ".".join(map(str, error["loc"])),
                "type": error["type"],
                "message": validation_message(".".join(map(str, error["loc"])), error["type"]),
            }
            for error in exc.errors()
        ]
        message = "；".join(dict.fromkeys(field["message"] for field in fields))
        return error_response(422, "validation_error", message, {"fields": fields})

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(
            exc.status_code, "http_error", "请求的资源不可用，请检查地址和请求方式"
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error(
            "Database operation failed (%s); check connectivity and migrations", type(exc).__name__
        )
        return error_response(
            503, "database_unavailable", "数据库暂不可用，请检查数据库连接并执行迁移后重试"
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Request failed (%s)", type(exc).__name__)
        return error_response(500, "internal_error", "服务暂时不可用，请稍后重试或联系管理员")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(CaptureBodyLimit)
    app.include_router(router)

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    def missing_api(path: str) -> None:
        raise ClipoError(404, "not_found", "接口不存在，请检查 API 地址与版本")

    if settings.static_path.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_path, html=True), name="frontend")
    return app
