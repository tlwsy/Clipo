import hashlib
import json
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.capture_repository import CaptureRepository
from app.errors import ClipoError
from app.extractors.base import CapturedContent
from app.models import CaptureJob
from app.schemas.capture import CaptureRequest, UploadRequest
from app.schemas.payload import CapturePayload
from app.upload_repository import UploadRepository


def fingerprint(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def submit(repository: CaptureRepository, request: CaptureRequest, key: str | None) -> CaptureJob:
    payload = request.payload.model_dump(mode="json") if request.payload else None
    job = repository.create_job(
        request.url,
        key,
        payload=payload,
        request_hash=fingerprint(payload) if payload is not None else None,
    )
    repository.db.commit()
    return job


def start_upload(
    repository: UploadRepository, request: UploadRequest, key: str | None
) -> CaptureJob:
    job = repository.create_job(
        request.url, key, uploading=True, request_hash=fingerprint(request.model_dump(mode="json"))
    )
    repository.start_upload(job, request.total_bytes, request.sha256)
    repository.db.commit()
    return job


def complete_upload(repository: UploadRepository, job_id: str) -> CaptureJob:
    job = repository.job(job_id)
    if job.status != "uploading" and job.payload is not None:
        return job
    upload = repository.locked_upload(job_id)
    try:
        payload = CapturePayload.model_validate_json(repository.assembled(upload))
    except ValidationError as exc:
        raise ClipoError(422, "invalid_payload", "页面内容格式无效，请更新扩展后重新保存") from exc
    job.payload = payload.model_dump(mode="json")
    job.status = "queued"
    repository.delete_upload(job_id)
    repository.db.commit()
    return job


def browser_content(url: str, payload: dict, max_comments: int) -> CapturedContent:
    data = CapturePayload.model_validate(payload).model_dump(exclude={"tags"})
    host = urlsplit(url).hostname
    platform = "web"
    if host in {"xiaohongshu.com", "www.xiaohongshu.com"}:
        platform = "xiaohongshu"
    elif host in {"xiaoheihe.cn", "www.xiaoheihe.cn", "api.xiaoheihe.cn"}:
        platform = "xiaoheihe"
    data["comments"] = data["comments"][:max_comments]
    return CapturedContent(
        url=url, platform=platform, comment_capture_limit=max_comments, extractor_version=1, **data
    )
