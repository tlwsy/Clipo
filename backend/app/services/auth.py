from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.base import utcnow
from app.errors import ClipoError
from app.models import User
from app.repositories import IdentityRepository, UserRepository
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    SetupRequest,
    UserResponse,
)
from app.security.credentials import (
    create_access_token,
    dummy_hash,
    hash_password,
    hash_token,
    new_token,
    password_hasher,
    verify_password,
)
from app.services.settings import update_llm


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.identities = IdentityRepository(db)

    def issue_session(self, user: User) -> SessionResponse:
        refresh = new_token("rt")
        self.identities.add_refresh(
            user.id,
            hash_token(refresh),
            utcnow() + timedelta(days=self.settings.refresh_token_ttl_days),
        )
        return SessionResponse(
            access_token=create_access_token(user.id, self.settings),
            refresh_token=refresh,
            expires_in=self.settings.access_token_ttl_seconds,
            user=UserResponse.model_validate(user),
        )

    def create_user(self, payload: RegisterRequest, *, admin: bool = False) -> User:
        try:
            return self.identities.create_user(
                payload.username, str(payload.email), hash_password(payload.password), admin
            )
        except IntegrityError as exc:
            raise ClipoError(409, "identity_exists", "用户名或邮箱已被使用，请更换后重试") from exc

    def setup(self, payload: SetupRequest) -> SessionResponse:
        if not self.identities.claim_setup():
            raise ClipoError(409, "setup_completed", "初始化已完成，请使用现有账号登录")
        user = self.create_user(payload, admin=True)
        if payload.llm is not None:
            update_llm(UserRepository(self.db, user.id), payload.llm, self.settings)
        return self.issue_session(user)

    def validate_setup(self) -> None:
        if self.identities.setup_completed():
            raise ClipoError(409, "setup_completed", "初始化已完成，请使用现有账号登录")

    def register(self, payload: RegisterRequest) -> SessionResponse:
        if not self.identities.setup_completed():
            raise ClipoError(409, "setup_required", "请先在设置向导中创建管理员")
        if not self.settings.registration_open:
            raise ClipoError(403, "registration_closed", "当前实例未开放注册，请联系管理员")
        return self.issue_session(self.create_user(payload))

    def login(self, payload: LoginRequest) -> SessionResponse:
        user = self.identities.by_username(payload.username)
        valid = verify_password(payload.password, user.password_hash if user else dummy_hash)
        if not user or not valid:
            raise ClipoError(401, "invalid_credentials", "用户名或密码错误，请检查后重试")
        if password_hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)
        return self.issue_session(user)

    def refresh(self, token: str | None) -> SessionResponse:
        user_id = self.identities.consume_refresh(hash_token(token)) if token else None
        user = self.identities.by_id(user_id) if user_id else None
        if user is None:
            raise ClipoError(401, "invalid_refresh_token", "登录已过期，请重新登录")
        return self.issue_session(user)

    def logout(self, token: str | None) -> None:
        if token:
            self.identities.revoke_refresh(hash_token(token))
