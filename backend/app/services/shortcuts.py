import json
from datetime import timedelta
from urllib.parse import quote, urlencode
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import ShortcutPairing
from app.repositories import IdentityRepository
from app.schemas.shortcuts import (
    IssuedPairing,
    PairingRequest,
    PairingStatus,
    ShortcutConfiguration,
)
from app.security.credentials import hash_token, new_token
from app.services.tokens import issue_token
from app.shortcut_repository import ShortcutRepository

SHORTCUT_NAME = "保存到 Clipo"
SETUP_PREFIX = "clipo-setup:"


def pairing_status(row: ShortcutPairing | None) -> PairingStatus:
    if row is None:
        raise ClipoError(404, "pairing_not_found", "此配置已取消或被替换，请重新配置设备")
    if row.consumed_at:
        status = "claimed" if row.token_id else "revoked"
    else:
        status = "pending" if row.expires_at > utcnow() else "expired"
    return PairingStatus(
        id=row.id, name=row.name, expires_at=row.expires_at, status=status, token_id=row.token_id
    )


def create_pairing(repository: ShortcutRepository, payload: PairingRequest) -> IssuedPairing:
    code = new_token("cp")
    row = repository.issue(
        uuid4().hex,
        hash_token(code),
        payload.name,
        payload.server_url,
        utcnow() + timedelta(minutes=5),
    )
    setup_input = SETUP_PREFIX + json.dumps(
        {"version": 1, "server_url": payload.server_url, "code": code}, separators=(",", ":")
    )
    launch_url = "shortcuts://run-shortcut?" + urlencode(
        {"name": SHORTCUT_NAME, "input": "text", "text": setup_input}, quote_via=quote
    )
    return IssuedPairing(
        **pairing_status(row).model_dump(), setup_input=setup_input, launch_url=launch_url
    )


def consume_pairing(db: Session, code: str) -> ShortcutConfiguration:
    code_hash = hash_token(code)
    user_id = IdentityRepository(db).shortcut_pairing_owner(code_hash)
    row = ShortcutRepository(db, user_id).consume(code_hash) if user_id is not None else None
    if row is None:
        raise ClipoError(
            400, "pairing_unavailable", "配置码无效、已过期或已使用，请回到 Clipo 重新配置设备"
        )
    issued = issue_token(ShortcutRepository(db, row.user_id), row.name)
    row.token_id = issued.id
    # Consumption and token creation commit together in the request's transaction.
    return ShortcutConfiguration(server_url=row.server_url, token=issued.token, token_id=issued.id)
