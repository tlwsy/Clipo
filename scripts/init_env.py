"""Create a local configuration without overwriting an existing deployment."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env already exists; leaving it unchanged.")
else:
    content = (root / ".env.example").read_text()
    content = content.replace(
        "CLIPO_SECRET_KEY=\n", f"CLIPO_SECRET_KEY={secrets.token_hex(32)}\n", 1
    )
    content = content.replace(
        "POSTGRES_PASSWORD=clipo-local-change-me", f"POSTGRES_PASSWORD={secrets.token_hex(24)}", 1
    )
    with target.open("x") as config:
        config.write(content)
    target.chmod(0o600)
    print("Created .env with fresh secret keys. Keep this file private and backed up.")
