"""对已有的本机 MinIO 与 WebDAV 测试服务执行实际上传/读取；仅用固定测试凭据。"""

import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

from app.config import Settings
from app.security.credentials import encrypt_secret
from app.storage.backup import store_backup


def curl(url: str, *, s3: bool = False, method: str = "GET") -> bytes:
    command = ["curl", "--silent", "--show-error", "--fail", "--max-time", "30", "-X", method]
    if s3:
        command.extend(
            ["--aws-sigv4", "aws:amz:us-east-1:s3", "--user", "clipo-test:clipo-test-secret"]
        )
    command.append(url)
    return subprocess.check_output(command)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="clipo-storage-check-") as directory:
        path = Path(directory) / "archive.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("library.json", json.dumps({"notes": ["测试中文内容"]}))
        settings = Settings(
            _env_file=None,
            secret_key="test-storage-key-at-least-32-characters",
            backup_allowed_origins=["http://127.0.0.1:59000", "http://127.0.0.1:59001"],
        )
        curl("http://127.0.0.1:59000/clipo-backup-check", s3=True, method="PUT")
        for target, port in (("s3", 59000), ("webdav", 59001)):
            config = {
                "target": target,
                "endpoint": f"http://127.0.0.1:{port}",
                "bucket": "clipo-backup-check",
                "region": "us-east-1",
                "prefix": "",
                "username": "test",
                "secret": encrypt_secret("clipo-test-secret", settings),
                "access_key": encrypt_secret("clipo-test", settings),
            }
            for _ in range(2):
                store_backup(path, 1, "wire-check", config, settings)
            prefix = "/clipo-backup-check" if target == "s3" else ""
            actual = curl(f"http://127.0.0.1:{port}{prefix}/1-wire-check.zip", s3=target == "s3")
            assert actual == path.read_bytes()
            with zipfile.ZipFile(io.BytesIO(actual)) as archive:
                assert json.loads(archive.read("library.json"))["notes"] == ["测试中文内容"]
            print(f"{target} 实机上传、幂等覆盖与下载内容校验通过")


if __name__ == "__main__":
    main()
