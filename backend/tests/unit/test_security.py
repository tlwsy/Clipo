# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from app.config import Settings
from app.errors import ClipoError
from app.security.credentials import decrypt_secret, encrypt_secret
from pydantic import ValidationError


def test_secret_key_must_be_configured_and_strong() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key="too-short")


def test_changed_encryption_key_gives_actionable_error() -> None:
    first = Settings(_env_file=None, secret_key="first-test-key-at-least-32-characters")
    second = Settings(_env_file=None, secret_key="second-test-key-at-least-32-characters")
    encrypted = encrypt_secret("private-key", first)
    assert decrypt_secret(encrypted, first) == "private-key"
    with pytest.raises(ClipoError) as caught:
        decrypt_secret(encrypted, second)
    assert caught.value.code == "secret_unavailable"
