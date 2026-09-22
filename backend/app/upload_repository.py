# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
from datetime import timedelta

from sqlalchemy import delete, select, update

from app.capture_repository import CaptureRepository
from app.db.base import utcnow
from app.errors import ClipoError
from app.models import CaptureJob, CaptureUpload, CaptureUploadChunk
from app.schemas.payload import CHUNK_BYTES


class UploadRepository(CaptureRepository):
    def start_upload(self, job: CaptureJob, total_bytes: int, digest: str) -> None:
        if job.status != "uploading":
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert = sqlite_insert if self.db.bind.dialect.name == "sqlite" else pg_insert
        self.db.execute(
            insert(CaptureUpload)
            .values(
                job_id=job.id,
                user_id=self.user_id,
                total_bytes=total_bytes,
                sha256=digest,
                expires_at=utcnow() + timedelta(hours=1),
            )
            .on_conflict_do_nothing(index_elements=["job_id"])
        )

    def locked_upload(self, job_id: str) -> CaptureUpload:
        self.job(job_id)
        result = self.db.execute(
            update(CaptureJob)
            .where(
                CaptureJob.id == job_id,
                CaptureJob.user_id == self.user_id,
                CaptureJob.status == "uploading",
            )
            .values(updated_at=utcnow())
        )
        if result.rowcount != 1:
            raise ClipoError(409, "upload_closed", "上传已结束，请刷新任务状态或重新保存页面")
        upload = self.db.scalar(
            select(CaptureUpload).where(
                CaptureUpload.job_id == job_id,
                CaptureUpload.user_id == self.user_id,
            )
        )
        if upload is None or upload.expires_at <= utcnow():
            raise ClipoError(410, "upload_expired", "上传已过期，请重新保存页面")
        return upload

    def put_chunk(self, job_id: str, position: int, data: bytes) -> None:
        upload = self.locked_upload(job_id)
        size = min(CHUNK_BYTES, upload.total_bytes - position * CHUNK_BYTES)
        if size <= 0 or len(data) != size:
            raise ClipoError(422, "invalid_chunk", "分块位置或长度不正确，请更新扩展后重新保存")
        existing = self.db.scalar(
            select(CaptureUploadChunk)
            .join(CaptureUpload)
            .where(
                CaptureUpload.user_id == self.user_id,
                CaptureUploadChunk.job_id == job_id,
                CaptureUploadChunk.position == position,
            )
        )
        if existing:
            if existing.data != data:
                raise ClipoError(409, "chunk_conflict", "该分块已有不同内容，请重新保存页面")
            return
        self.db.add(CaptureUploadChunk(job_id=job_id, position=position, data=data))

    def assembled(self, upload: CaptureUpload) -> bytes:
        chunks = list(
            self.db.scalars(
                select(CaptureUploadChunk)
                .join(CaptureUpload)
                .where(
                    CaptureUpload.user_id == self.user_id,
                    CaptureUploadChunk.job_id == upload.job_id,
                )
                .order_by(CaptureUploadChunk.position)
            )
        )
        count = (upload.total_bytes + CHUNK_BYTES - 1) // CHUNK_BYTES
        if [chunk.position for chunk in chunks] != list(range(count)):
            raise ClipoError(409, "upload_incomplete", "内容尚未全部上传，请继续上传缺失分块")
        data = b"".join(chunk.data for chunk in chunks)
        if len(data) != upload.total_bytes or hashlib.sha256(data).hexdigest() != upload.sha256:
            raise ClipoError(422, "upload_checksum", "内容校验失败，请重新保存页面")
        return data

    def delete_upload(self, job_id: str) -> None:
        self.db.execute(
            delete(CaptureUpload).where(
                CaptureUpload.job_id == job_id,
                CaptureUpload.user_id == self.user_id,
            )
        )

    def expire_upload(self, job_id: str) -> None:
        result = self.db.execute(
            update(CaptureJob)
            .where(
                CaptureJob.id == job_id,
                CaptureJob.user_id == self.user_id,
                CaptureJob.status == "uploading",
            )
            .values(
                status="failed", last_error="页面上传已过期，请从扩展重新保存", updated_at=utcnow()
            )
        )
        if result.rowcount:
            self.delete_upload(job_id)
