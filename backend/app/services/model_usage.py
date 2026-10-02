# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.llm.client import CompatibleClient
from app.model_usage_repository import ModelUsageRepository


def reserve_model_call(sessions: sessionmaker[Session], user_id: int) -> None:
    # Persist before contacting the provider. Failed/uncertain requests still count,
    # since a timeout or crash cannot prove the provider did not bill the request.
    with sessions.begin() as db:
        ModelUsageRepository(db, user_id).reserve()


class MeteredClient(CompatibleClient):
    def __init__(
        self, client: CompatibleClient, sessions: sessionmaker[Session], user_id: int
    ) -> None:
        self.client, self.sessions, self.user_id = client, sessions, user_id

    def complete(self, **kwargs: Any) -> str:
        reserve_model_call(self.sessions, self.user_id)
        return self.client.complete(**kwargs)
