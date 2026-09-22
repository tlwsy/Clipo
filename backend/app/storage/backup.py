# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import base64
import hashlib
import hmac
import os
import shutil
import socket
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from app.config import Settings
from app.security.credentials import decrypt_secret
from app.security.urls import public_addresses
from app.services.backup_settings import validate_endpoint


def sign_s3(
    url: str, digest: str, access_key: str, secret: str, region: str, now: datetime | None = None
) -> dict[str, str]:
    now = now or datetime.now(UTC)
    stamp, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    parts = urlsplit(url)
    headers = {"host": parts.netloc, "x-amz-content-sha256": digest, "x-amz-date": stamp}
    signed = ";".join(headers)
    canonical = "\n".join(
        ["PUT", parts.path, "", "".join(f"{k}:{v}\n" for k, v in headers.items()), signed, digest]
    )
    scope = f"{day}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = ("AWS4" + secret).encode()
    for part in (day, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed}, Signature={signature}"
    )
    return headers


def put_file(url: str, path: Path, headers: dict[str, str], settings: Settings) -> None:
    validate_endpoint(url, settings)
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin in settings.backup_allowed_origins:
        addresses = list(
            dict.fromkeys(
                record[4][0]
                for record in socket.getaddrinfo(
                    parts.hostname,
                    parts.port or (443 if parts.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            )
        )
    else:
        addresses = public_addresses(url)
    if not addresses:
        raise OSError("Backup DNS failed")
    deadline = time.monotonic() + 180

    def chunks() -> Iterator[bytes]:
        with path.open("rb") as stream:
            while data := stream.read(64 * 1024):
                if time.monotonic() > deadline:
                    raise TimeoutError()
                yield data

    with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
        with client.stream(
            "PUT",
            httpx.URL(url).copy_with(host=addresses[0]),
            content=chunks(),
            headers={
                **{key.lower(): value for key, value in headers.items()},
                "host": parts.netloc,
                "Content-Length": str(path.stat().st_size),
                "Content-Type": "application/zip",
            },
            extensions={"sni_hostname": parts.hostname},
        ) as response:
            if response.status_code not in (200, 201, 204):
                # Never read/log upstream bodies, paths or credentials.
                raise OSError("Backup destination rejected upload")


def store_backup(path: Path, user_id: int, job_id: str, config: dict, settings: Settings) -> None:
    name = f"{job_id}.zip"
    if config["target"] == "local":
        directory = settings.backup_path / str(user_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = directory / f".{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output, path.open("rb") as source:
                os.chmod(temporary, 0o600)
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(directory / name)
            completed = sorted(
                directory.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True
            )
            for old in completed[settings.backup_keep :]:
                old.unlink(missing_ok=True)
        finally:
            temporary.unlink(missing_ok=True)
        return
    endpoint = validate_endpoint(config["endpoint"], settings)
    prefix = config.get("prefix", "clipo").strip("/")
    # WebDAV's configured directory must exist; one account-specific filename needs no MKCOL.
    object_key = f"{prefix + '/' if prefix else ''}{user_id}-{name}"
    secret = decrypt_secret(config["secret"], settings)
    if config["target"] == "s3":
        url = endpoint + "/" + quote(config["bucket"], safe="") + "/" + quote(object_key, safe="/")
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        headers = sign_s3(
            url, digest, decrypt_secret(config["access_key"], settings), secret, config["region"]
        )
    else:
        url = endpoint + "/" + quote(object_key, safe="/")
        credential = base64.b64encode(f"{config['username']}:{secret}".encode()).decode()
        headers = {"Authorization": f"Basic {credential}"}
    put_file(url, path, headers, settings)
