# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import plistlib

from fastapi import APIRouter, Response

from app.api.dependencies import Config, Db, UserRepo
from app.errors import ClipoError
from app.schemas.shortcuts import (
    ConsumePairing,
    IssuedPairing,
    PairingRequest,
    PairingStatus,
    ShortcutConfiguration,
    ShortcutInfo,
)
from app.services import shortcuts as service
from app.services.shortcut_template import build_shortcut
from app.shortcut_repository import ShortcutRepository

router = APIRouter(prefix="/shortcuts", tags=["shortcuts"])


@router.get("/info", response_model=ShortcutInfo)
def info(settings: Config) -> ShortcutInfo:
    return ShortcutInfo(install_url=settings.shortcut_install_url)


@router.get("/template", response_class=Response)
def template() -> Response:
    return Response(
        content=plistlib.dumps(build_shortcut(), fmt=plistlib.FMT_XML, sort_keys=False),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="clipo-save.unsigned.shortcut"'},
    )


@router.post("/pairings", response_model=IssuedPairing, status_code=201)
def issue_pairing(payload: PairingRequest, repository: UserRepo) -> IssuedPairing:
    return service.create_pairing(ShortcutRepository(repository.db, repository.user_id), payload)


@router.get("/pairings/{identifier}", response_model=PairingStatus)
def pairing_status(identifier: str, repository: UserRepo) -> PairingStatus:
    return service.pairing_status(
        ShortcutRepository(repository.db, repository.user_id).get(identifier)
    )


@router.delete("/pairings/{identifier}", status_code=204)
def cancel_pairing(identifier: str, repository: UserRepo) -> None:
    if not ShortcutRepository(repository.db, repository.user_id).cancel(identifier):
        raise ClipoError(
            409,
            "pairing_not_pending",
            "此配置已领取、取消或被替换；已领取的 Token 请在令牌列表撤销",
        )


@router.post("/pairings/consume", response_model=ShortcutConfiguration)
def consume_pairing(payload: ConsumePairing, db: Db) -> ShortcutConfiguration:
    return service.consume_pairing(db, payload.code.get_secret_value())
