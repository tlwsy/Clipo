import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import Config, CurrentUser, Db
from app.backup_repository import BackupRepository
from app.errors import ClipoError
from app.schemas.backup import MAX_IMPORT_BYTES, BackupJobResponse, ExportRequest
from app.services.backup import download_path, job_directory

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("", response_model=list[BackupJobResponse])
def jobs(db: Db, user: CurrentUser) -> list[BackupJobResponse]:
    return [
        BackupJobResponse.model_validate(job) for job in BackupRepository(db, user.id).backup_jobs()
    ]


@router.post("/exports", response_model=BackupJobResponse, status_code=202)
def export(body: ExportRequest, request: Request, db: Db, user: CurrentUser) -> BackupJobResponse:
    job = BackupRepository(db, user.id).create_backup_job("export", "export:" + body.request_key)
    db.commit()
    request.app.state.capture_queue.backups.enqueue(user.id, job.id)
    return BackupJobResponse.model_validate(job)


@router.post("/imports", response_model=BackupJobResponse, status_code=202)
async def import_library(
    request: Request, db: Db, user: CurrentUser, settings: Config
) -> BackupJobResponse:
    root = settings.queue_path.parent / "imports"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    fd, temporary = tempfile.mkstemp(dir=root)
    path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_IMPORT_BYTES:
                    raise ClipoError(413, "archive_too_large", "导入文件上限为 100 MiB")
                digest.update(chunk)
                await run_in_threadpool(output.write, chunk)
        if not size:
            raise ClipoError(422, "empty_archive", "请选择解压后的 library.json 文件")
        repository = BackupRepository(db, user.id)
        job = repository.create_backup_job("import", "import:" + digest.hexdigest())
        destination = job_directory(settings, user.id, job.id) / "input.json"
        if job.status == "queued" and not destination.exists():
            path.replace(destination)
        db.commit()
        request.app.state.capture_queue.backups.enqueue(user.id, job.id)
        return BackupJobResponse.model_validate(job)
    finally:
        path.unlink(missing_ok=True)


@router.get("/{job_id}/download", response_class=FileResponse)
def download(job_id: str, db: Db, user: CurrentUser, settings: Config) -> FileResponse:
    path = download_path(BackupRepository(db, user.id), settings, job_id)
    return FileResponse(path, media_type="application/zip", filename=f"clipo-{job_id}.zip")


@router.post("/{job_id}/retry", response_model=BackupJobResponse, status_code=202)
def retry(job_id: str, request: Request, db: Db, user: CurrentUser) -> BackupJobResponse:
    job = BackupRepository(db, user.id).retry_backup(job_id)
    db.commit()
    request.app.state.capture_queue.backups.enqueue(user.id, job.id)
    return BackupJobResponse.model_validate(job)
