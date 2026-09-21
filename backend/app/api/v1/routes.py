from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from app import __version__
from app.api.dependencies import Config, CurrentUser, Db, UserRepo
from app.api.v1.captures import router as captures_router
from app.models import User
from app.platform_repository import PlatformCheckRepository
from app.repositories import IdentityRepository
from app.schemas.auth import (
    ErrorResponse,
    IssuedTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    SetupRequest,
    TokenRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.settings import (
    CapabilitiesResponse,
    PlatformCheckResponse,
    PlatformChecksResponse,
    PlatformName,
    SettingsResponse,
    SettingsUpdate,
    VersionResponse,
)
from app.services import tokens as token_service
from app.services.auth import AuthService
from app.services.settings import (
    read_settings,
    update_capture_settings,
    update_llm,
    update_platform_cookies,
)

router = APIRouter(
    prefix="/api/v1",
    responses={
        status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 422, 500, 503)
    },
)
COOKIE_NAME = "clipo_refresh"
router.include_router(captures_router)
COOKIE_PATH = "/api/v1/auth"


def attach_session(
    response: Response, session: SessionResponse, settings: Config
) -> SessionResponse:
    response.set_cookie(
        COOKIE_NAME,
        session.refresh_token,
        httponly=True,
        secure=settings.base_url.startswith("https://"),
        samesite="strict",
        max_age=settings.refresh_token_ttl_days * 86400,
        path=COOKIE_PATH,
    )
    return session


@router.get("/health", tags=["meta"])
def health(db: Db) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/meta/version", response_model=VersionResponse, tags=["meta"])
def version(db: Db, settings: Config) -> VersionResponse:
    return VersionResponse(
        version=__version__,
        setup_completed=IdentityRepository(db).setup_completed(),
        registration_open=settings.registration_open,
    )


@router.get("/meta/capabilities", response_model=CapabilitiesResponse, tags=["meta"])
def capabilities(repository: UserRepo, settings: Config, request: Request) -> CapabilitiesResponse:
    llm = read_settings(repository, settings).llm
    return CapabilitiesResponse(
        fulltext_search=request.app.state.search.mode,
        llm_configured=bool(llm.api_key_set and llm.base_url and llm.model),
        registration_open=settings.registration_open,
    )


@router.post("/setup", response_model=SessionResponse, status_code=201, tags=["setup"])
def setup(payload: SetupRequest, response: Response, db: Db, settings: Config) -> SessionResponse:
    return attach_session(response, AuthService(db, settings).setup(payload), settings)


@router.post("/setup/validate", status_code=204, tags=["setup"])
def validate_setup(payload: RegisterRequest, db: Db, settings: Config) -> None:
    """Validate the account step without creating a user or claiming initialization."""
    AuthService(db, settings).validate_setup()


@router.post("/auth/register", response_model=SessionResponse, status_code=201, tags=["auth"])
def register(
    payload: RegisterRequest, response: Response, db: Db, settings: Config
) -> SessionResponse:
    return attach_session(response, AuthService(db, settings).register(payload), settings)


@router.post("/auth/login", response_model=SessionResponse, tags=["auth"])
def login(payload: LoginRequest, response: Response, db: Db, settings: Config) -> SessionResponse:
    return attach_session(response, AuthService(db, settings).login(payload), settings)


@router.post("/auth/refresh", response_model=SessionResponse, tags=["auth"])
def refresh(
    payload: RefreshRequest, request: Request, response: Response, db: Db, settings: Config
) -> SessionResponse:
    token = payload.refresh_token or request.cookies.get(COOKIE_NAME)
    return attach_session(response, AuthService(db, settings).refresh(token), settings)


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(
    payload: RefreshRequest, request: Request, response: Response, db: Db, settings: Config
) -> None:
    AuthService(db, settings).logout(payload.refresh_token or request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)


@router.get("/auth/me", response_model=UserResponse, tags=["auth"])
def me(user: CurrentUser) -> User:
    return user


@router.get("/tokens", response_model=list[TokenResponse], tags=["tokens"])
def tokens(repository: UserRepo) -> list[TokenResponse]:
    return token_service.list_tokens(repository)


@router.post("/tokens", response_model=IssuedTokenResponse, status_code=201, tags=["tokens"])
def issue_token(payload: TokenRequest, repository: UserRepo) -> IssuedTokenResponse:
    return token_service.issue_token(repository, payload.name)


@router.delete("/tokens/{token_id}", status_code=204, tags=["tokens"])
def delete_token(token_id: int, repository: UserRepo) -> None:
    token_service.revoke_token(repository, token_id)


@router.get("/settings", response_model=SettingsResponse, tags=["settings"])
def get_user_settings(repository: UserRepo, settings: Config) -> SettingsResponse:
    return read_settings(repository, settings)


@router.put("/settings", response_model=SettingsResponse, tags=["settings"])
def put_user_settings(
    payload: SettingsUpdate, repository: UserRepo, settings: Config
) -> SettingsResponse:
    if payload.llm is not None:
        update_llm(repository, payload.llm, settings)
    if payload.platform_cookies is not None:
        update_platform_cookies(repository, payload.platform_cookies, settings)
    if payload.capture is not None:
        update_capture_settings(repository, payload.capture)
    return read_settings(repository, settings)


@router.get("/settings/platform-checks", response_model=PlatformChecksResponse, tags=["settings"])
def platform_checks(repository: UserRepo) -> PlatformChecksResponse:
    checks = PlatformCheckRepository(repository.db, repository.user_id)
    return PlatformChecksResponse(
        xiaohongshu=checks.status("xiaohongshu"),
        xiaoheihe=checks.status("xiaoheihe"),
    )


@router.post(
    "/settings/platform-checks/{platform}",
    response_model=PlatformCheckResponse,
    status_code=202,
    tags=["settings"],
)
def request_platform_check(
    platform: PlatformName,
    repository: UserRepo,
    request: Request,
) -> PlatformCheckResponse:
    checks = PlatformCheckRepository(repository.db, repository.user_id)
    row = checks.request(platform)
    request_id = row.request_id
    response = checks.status(platform)
    repository.db.commit()
    request.app.state.capture_queue.platform_checks.enqueue(
        repository.user_id, platform, request_id
    )
    return response
