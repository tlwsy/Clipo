# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from app.backup_repository import BackupRepository
from app.db.base import utcnow
from app.models import UserSettings
from app.security.credentials import decrypt_secret
from app.security.urls import UnsafeURL
from app.storage.backup import put_file, store_backup
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.integration.test_backups import run_job
from tests.integration.test_note_organization import seed_note


def test_backup_configuration_credentials_and_endpoint_changes(
    app: FastAPI, client: TestClient, auth: dict
) -> None:
    body = {
        "target": "s3",
        "endpoint": "https://storage.example.com",
        "bucket": "notes",
        "access_key": "example-access",
        "secret": "example-secret",
        "schedule": "0 4 * * *",
    }
    response = client.put("/api/v1/backups/settings", headers=auth, json=body)
    assert response.status_code == 200, response.text
    assert "example-secret" not in response.text and "example-access" not in response.text
    with app.state.session_factory() as db:
        stored = db.get(UserSettings, 1).backup_config
        assert stored["secret"] != body["secret"]
        assert decrypt_secret(stored["secret"], app.state.settings) == body["secret"]
    del body["secret"], body["access_key"]
    assert client.put("/api/v1/backups/settings", headers=auth, json=body).status_code == 200
    body["endpoint"] = "https://different.example.com"
    assert client.put("/api/v1/backups/settings", headers=auth, json=body).status_code == 422
    assert (
        client.get("/api/v1/backups/settings", headers=auth).json()["endpoint"]
        == "https://storage.example.com"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"endpoint": "http://storage.example.com"},
        {"endpoint": "https://127.0.0.1"},
        {"endpoint": "https://user:password@example.com"},
        {"endpoint": "https://example.com/?secret=x"},
        {"schedule": "junk"},
        {"schedule": "bad 4 * * *"},
        {"schedule": "*/0 * * * *"},
        {"prefix": "../escape"},
        {"prefix": "/absolute"},
    ],
)
def test_invalid_target_configuration(client: TestClient, auth: dict, change: dict) -> None:
    body = {
        "target": "webdav",
        "endpoint": "https://dav.example.com",
        "username": "test",
        "secret": "password",
        **change,
    }
    assert client.put("/api/v1/backups/settings", headers=auth, json=body).status_code == 422
    assert client.get("/api/v1/backups/settings", headers=auth).json()["target"] == "none"


def test_scheduled_local_backup_retention_and_download_expiration(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_note(app)
    app.state.settings.backup_keep = 1
    assert (
        client.put(
            "/api/v1/backups/settings",
            headers=auth,
            json={"target": "local", "schedule": "0 4 * * *"},
        ).status_code
        == 200
    )
    queue = app.state.capture_queue.backups
    monkeypatch.setattr("app.tasks.backup.utcnow", lambda: datetime(2026, 9, 22, 20, 0, tzinfo=UTC))
    queue.schedule()
    queue.schedule()
    jobs = client.get("/api/v1/backups", headers=auth).json()
    assert len(jobs) == 1
    queue.run(1, jobs[0]["id"])
    job = run_job(app, client, auth, "/api/v1/backups/run", json={"request_key": "manual"})
    assert job["status"] == "success", job
    files = list((app.state.settings.backup_path / "1").glob("*.zip"))
    assert len(files) == 1 and files[0].name == job["id"] + ".zip"
    with zipfile.ZipFile(files[0]) as archive:
        assert len(json.loads(archive.read("library.json"))["notes"]) == 1
    with app.state.session_factory.begin() as db:
        BackupRepository(db, 1).backup_job(job["id"]).updated_at = utcnow() - timedelta(days=10)
    queue.cleanup()
    assert client.get(f"/api/v1/backups/{job['id']}/download", headers=auth).status_code == 410
    assert files[0].exists()


@pytest.mark.parametrize("target", ["s3", "webdav"])
def test_remote_backup_uploads_restorable_zip_without_redirects(
    app: FastAPI, client: TestClient, auth: dict, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    seed_note(app)
    body = {
        "target": target,
        "endpoint": "https://storage.example.com",
        "bucket": "notes",
        "region": "us-east-1",
        "username": "test",
        "access_key": "key",
        "secret": "password",
    }
    assert client.put("/api/v1/backups/settings", headers=auth, json=body).status_code == 200
    requests = []

    def upload(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "storage.example.com"
        assert request.extensions["sni_hostname"] == "storage.example.com"
        with zipfile.ZipFile(io.BytesIO(request.read())) as archive:
            assert len(json.loads(archive.read("library.json"))["notes"]) == 1
        return httpx.Response(201)

    original_client = httpx.Client
    monkeypatch.setattr("app.storage.backup.public_addresses", lambda url: ["93.184.216.34"])
    monkeypatch.setattr(
        "app.storage.backup.httpx.Client",
        lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(upload)),
    )
    job = run_job(app, client, auth, "/api/v1/backups/run", json={"request_key": "remote"})
    assert job["status"] == "success", job
    request = requests[0]
    assert request.url.path.endswith(f"1-{job['id']}.zip")
    assert request.headers["Authorization"].startswith(
        "AWS4-HMAC-SHA256" if target == "s3" else "Basic "
    )


def test_remote_redirect_is_rejected_and_private_dns_never_receives_secret(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "archive.zip"
    path.write_bytes(b"private notes")
    calls = []

    def redirect(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://other.example.com"})

    original_client = httpx.Client
    monkeypatch.setattr(
        "app.storage.backup.httpx.Client",
        lambda **kwargs: original_client(**kwargs, transport=httpx.MockTransport(redirect)),
    )
    monkeypatch.setattr(
        "app.security.urls.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(UnsafeURL):
        put_file(
            "https://dav.example.com/notes.zip",
            path,
            {"Authorization": "secret"},
            app.state.settings,
        )
    assert calls == []
    monkeypatch.setattr("app.storage.backup.public_addresses", lambda url: ["93.184.216.34"])
    with pytest.raises(OSError):
        put_file(
            "https://dav.example.com/notes.zip",
            path,
            {"Authorization": "secret"},
            app.state.settings,
        )
    assert len(calls) == 1


def test_local_failed_copy_keeps_previous_backup(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "archive.zip"
    path.write_bytes(b"first archive")
    store_backup(path, 1, "first", {"target": "local"}, app.state.settings)

    def fail(*args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("app.storage.backup.shutil.copyfileobj", fail)
    with pytest.raises(OSError):
        store_backup(path, 1, "second", {"target": "local"}, app.state.settings)
    directory = app.state.settings.backup_path / "1"
    assert [item.name for item in directory.iterdir()] == ["first.zip"]
