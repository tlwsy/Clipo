# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.db.base import utcnow
from app.errors import ClipoError
from app.models import ModelUsage, UserSettings
from app.repositories import UserRepository
from app.schemas.model_usage import ModelUsageResponse

QUOTA_MESSAGE = "本月模型调用次数已达上限，请在设置中调整限额，或下月再重试"


class ModelQuotaExceeded(ClipoError):
    def __init__(self) -> None:
        super().__init__(
            429,
            "model_quota_exceeded",
            QUOTA_MESSAGE,
        )


def month_window() -> tuple[str, datetime]:
    now = utcnow().astimezone(UTC)
    reset = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=UTC)
    return now.strftime("%Y-%m"), reset


class ModelUsageRepository(UserRepository):
    def status(self) -> ModelUsageResponse:
        month, reset = month_window()
        limit = self.settings().monthly_model_limit
        calls = (
            self.db.scalar(
                select(ModelUsage.calls).where(
                    ModelUsage.user_id == self.user_id, ModelUsage.month == month
                )
            )
            or 0
        )
        return ModelUsageResponse(
            month=month,
            resets_at=reset,
            monthly_limit=limit,
            calls=calls,
            remaining=None if limit is None else max(0, limit - calls),
        )

    def set_limit(self, limit: int | None) -> None:
        self.db.execute(
            update(UserSettings)
            .where(UserSettings.user_id == self.user_id)
            .values(monthly_model_limit=limit)
        )

    def reserve(self) -> None:
        # A real UPDATE locks on both SQLite and PostgreSQL, including the first call
        # of a month. Serialize quota edits with reservations, never with remote I/O.
        row = self.db.execute(
            update(UserSettings)
            .where(UserSettings.user_id == self.user_id)
            .values(monthly_model_limit=UserSettings.monthly_model_limit)
            .returning(UserSettings.monthly_model_limit)
        ).one_or_none()
        if row is None:
            raise ClipoError(401, "authentication_required", "账号不存在，无法调用模型")
        limit = row[0]
        month, _ = month_window()
        usage = self.db.scalar(
            select(ModelUsage).where(ModelUsage.user_id == self.user_id, ModelUsage.month == month)
        )
        calls = usage.calls if usage else 0
        if limit is not None and calls >= limit:
            raise ModelQuotaExceeded()
        if usage is None:
            self.db.add(ModelUsage(user_id=self.user_id, month=month, calls=1))
        else:
            usage.calls += 1
