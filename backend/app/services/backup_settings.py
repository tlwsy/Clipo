# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from huey import crontab

from app.config import Settings
from app.errors import ClipoError
from app.repositories import UserRepository
from app.schemas.backup import BackupSettingsResponse, BackupSettingsUpdate
from app.security.credentials import encrypt_secret
from app.security.urls import normalize_url


def schedule_match(expression: str) -> Callable[[datetime], bool]:
    minute, hour, day, month, weekday = expression.split()
    return crontab(minute=minute, hour=hour, day=day, month=month, day_of_week=weekday, strict=True)


def validate_endpoint(endpoint: str, settings: Settings) -> str:
    try:
        parts = urlsplit(endpoint)
        if (
            not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or "\\" in endpoint
            or any(ord(char) < 33 for char in endpoint)
        ):
            raise ValueError()
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in settings.backup_allowed_origins:
            if parts.scheme not in ("http", "https"):
                raise ValueError()
            return endpoint.rstrip("/")
        normalized = normalize_url(endpoint)
        if parts.scheme != "https" or parts.port not in (None, 443):
            raise ValueError()
        return normalized.rstrip("/")
    except Exception as exc:
        raise ClipoError(
            422,
            "invalid_backup_endpoint",
            "备份地址须为公开 HTTPS 地址；内网服务需管理员配置允许的 origin",
        ) from exc


def read_backup_settings(repository: UserRepository, settings: Settings) -> BackupSettingsResponse:
    stored = repository.settings().backup_config
    defaults = BackupSettingsUpdate().model_dump(
        exclude={"access_key", "secret", "clear_credentials"}
    )
    return BackupSettingsResponse(
        **{**defaults, **{key: stored[key] for key in defaults if key in stored}},
        access_key_set=bool(stored.get("access_key")),
        secret_set=bool(stored.get("secret")),
        timezone=settings.timezone,
        local_keep=settings.backup_keep,
        download_retention_days=settings.export_retention_days,
    )


def save_backup_settings(
    repository: UserRepository, body: BackupSettingsUpdate, settings: Settings
) -> BackupSettingsResponse:
    values = body.model_dump(exclude={"access_key", "secret", "clear_credentials"})
    values["schedule"] = body.schedule.strip()
    if body.schedule.strip():
        try:
            schedule_match(body.schedule)
            ZoneInfo(settings.timezone)
        except Exception as exc:
            raise ClipoError(
                422, "invalid_schedule", "请填写有效的五段 Cron 表达式并检查服务器时区"
            ) from exc
    if body.target in ("s3", "webdav"):
        values["endpoint"] = validate_endpoint(body.endpoint, settings)
    if body.target == "s3" and (not body.bucket or ".." in body.bucket):
        raise ClipoError(422, "invalid_bucket", "请填写 S3 存储桶名称")
    if "//" in body.prefix or body.prefix.startswith("/"):
        raise ClipoError(422, "invalid_prefix", "备份目录应为相对路径，例如 clipo/backups")
    previous = repository.settings().backup_config
    same_target = all(
        previous.get(key) == values[key] for key in ("target", "endpoint", "username")
    )
    for name in ("secret", "access_key"):
        provided = getattr(body, name)
        if provided and provided.get_secret_value():
            values[name] = encrypt_secret(provided.get_secret_value(), settings)
        elif same_target and not body.clear_credentials and previous.get(name):
            values[name] = previous[name]
    if body.target in ("s3", "webdav") and not values.get("secret"):
        raise ClipoError(422, "backup_credentials_required", "请填写目标服务的密钥或应用密码")
    if body.target == "s3" and not values.get("access_key"):
        raise ClipoError(422, "backup_credentials_required", "请填写 S3 Access Key")
    if body.target == "webdav" and not body.username:
        raise ClipoError(422, "backup_credentials_required", "请填写 WebDAV 用户名")
    repository.settings().backup_config = values
    return read_backup_settings(repository, settings)
