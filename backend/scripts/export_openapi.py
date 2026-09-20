"""Export API types without reading deployment credentials or touching the database."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.main import create_app

with TemporaryDirectory(prefix="clipo-openapi-") as directory:
    settings = Settings(
        _env_file=None,
        secret_key="openapi-generation-only-not-a-deployment-key",
        database_url="sqlite:///:memory:",
        queue_path=Path(directory) / "huey.db",
    )
    app = create_app(settings)
    target = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
    target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
    app.state.engine.dispose()
