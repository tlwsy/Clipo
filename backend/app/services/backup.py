# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import os
import re
import zipfile
from pathlib import Path

from app.backup_repository import BackupRepository
from app.config import Settings
from app.db.base import utcnow
from app.errors import ClipoError
from app.schemas.backup import MAX_IMPORT_BYTES
from app.services.notes import read_note


def job_directory(settings: Settings, user_id: int, job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ClipoError(404, "backup_not_found", "备份任务不存在")
    root = settings.queue_path.parent / "exports" / str(user_id) / job_id
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def write_archive(repository: BackupRepository, directory: Path, execution: str) -> tuple[str, int]:
    """Stream a consistent database snapshot into JSON and safe, numeric Markdown paths."""
    json_path = directory / f"{execution}.json"
    zip_path = directory / f"{execution}.zip"
    count = 0
    try:
        with (
            json_path.open("x", encoding="utf-8") as output,
            zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED) as archive,
        ):
            os.chmod(json_path, 0o600)
            os.chmod(zip_path, 0o600)
            header = {
                "format": "clipo-library",
                "version": 1,
                "exported_at": utcnow().isoformat(),
                "tags": [{"name": tag.name} for tag in repository.list_tags()],
            }
            output.write(json.dumps(header, ensure_ascii=False)[:-1] + ', "notes": [')
            for note_id in repository.note_ids():
                note = read_note(repository, note_id)
                note.content.raw_html = repository.note(note_id).content.get("raw_html")
                if count:
                    output.write(",")
                output.write(note.model_dump_json())
                if output.tell() > MAX_IMPORT_BYTES - 2:
                    raise ClipoError(422, "archive_too_large", "导出超过 100 MiB，请使用数据库备份")
                lines = [
                    f"# {note.title}",
                    "",
                    f"来源：{note.url}",
                    "",
                    "标签：" + "、".join(tag.name for tag in note.tags),
                    "",
                    "## 摘要",
                    "",
                    note.summary_markdown or "未生成摘要",
                    "",
                    "## 要点",
                    "",
                    *[f"- {point}" for point in note.key_points],
                    "",
                    "## 原文",
                    "",
                    note.content.text,
                    "",
                    "## 媒体引用",
                    "",
                    *note.content.images,
                    "",
                    "## 评论",
                    "",
                ]
                for comment in note.comments:
                    lines.extend(
                        [
                            f"### {comment.author or '匿名'}",
                            "",
                            comment.content,
                            f"点赞 {comment.likes} · 回复 {comment.replies}",
                            f"评分：{comment.ai_score}；{comment.ai_reason or '未评分'}",
                            "",
                        ]
                    )
                archive.writestr(f"markdown/{note.id}.md", "\n".join(lines))
                count += 1
                repository.db.expire_all()
            output.write("]}")
            output.flush()
            archive.write(json_path, "library.json")
    except BaseException:
        json_path.unlink(missing_ok=True)
        zip_path.unlink(missing_ok=True)
        raise
    finally:
        json_path.unlink(missing_ok=True)
    return zip_path.name, count


def download_path(repository: BackupRepository, settings: Settings, job_id: str) -> Path:
    job = repository.backup_job(job_id)
    if job.status != "success" or not job.artifact:
        raise ClipoError(409, "backup_not_ready", "导出尚未完成，请稍后刷新任务")
    path = job_directory(settings, repository.user_id, job.id) / job.artifact
    if not path.is_file():
        raise ClipoError(410, "backup_expired", "下载文件已清理，请重新导出")
    return path
