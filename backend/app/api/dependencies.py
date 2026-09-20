from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ClipoError
from app.models import User
from app.repositories import IdentityRepository, UserRepository
from app.security.credentials import decode_access_token, hash_token

bearer = HTTPBearer(auto_error=False)
api_token = APIKeyHeader(name="X-Clipo-Token", auto_error=False)


def get_config(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


Db = Annotated[Session, Depends(get_db, scope="function")]
Config = Annotated[Settings, Depends(get_config)]


def current_user(
    db: Db,
    settings: Config,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    token: Annotated[str | None, Depends(api_token)],
) -> User:
    identities = IdentityRepository(db)
    user = None
    if credentials:
        user = identities.by_id(decode_access_token(credentials.credentials, settings))
    elif token and token.startswith("ct_") and len(token) <= 256:
        user = identities.authenticate_api_token(hash_token(token))
    if user is None:
        raise ClipoError(401, "authentication_required", "请先登录，或检查 API Token 是否有效")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def user_repository(db: Db, user: CurrentUser) -> UserRepository:
    return UserRepository(db, user.id)


UserRepo = Annotated[UserRepository, Depends(user_repository)]
