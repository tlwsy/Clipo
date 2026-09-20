from app.errors import ClipoError
from app.repositories import UserRepository
from app.schemas.auth import IssuedTokenResponse, TokenResponse
from app.security.credentials import hash_token, new_token


def list_tokens(repository: UserRepository) -> list[TokenResponse]:
    return [TokenResponse.model_validate(token) for token in repository.list_tokens()]


def issue_token(repository: UserRepository, name: str) -> IssuedTokenResponse:
    raw = new_token("ct")
    token = repository.create_token(name, hash_token(raw))
    return IssuedTokenResponse(**TokenResponse.model_validate(token).model_dump(), token=raw)


def revoke_token(repository: UserRepository, token_id: int) -> None:
    if not repository.delete_token(token_id):
        raise ClipoError(404, "token_not_found", "此 API Token 不存在，请刷新列表")
