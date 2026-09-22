# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heybox web hkey protocol, checked against the official web bundle.

Algorithm reference: ParseHub (MIT), Copyright (c) 2024 梓澪.
See THIRD_PARTY_NOTICES.md and docs/platform-protocols.md.
"""

import hashlib
import secrets
import time
from itertools import zip_longest


def _double(value: int) -> int:
    return ((value << 1) ^ (27 if value & 128 else 0)) & 255


def _triple(value: int) -> int:
    return _double(value) ^ value


def _six(value: int) -> int:
    return _triple(_double(value))


def _mix(value: int) -> int:
    return _six(_triple(_double(value)))


def hkey(path: str, stamp: int, nonce: str) -> str:
    table = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"
    path = "/" + "/".join(part for part in path.split("/") if part) + "/"
    values = [
        "".join(table[:-2][ord(char) % len(table[:-2])] for char in str(stamp + 1)),
        "".join(table[ord(char) % len(table)] for char in path),
        "".join(table[ord(char) % len(table)] for char in nonce),
    ]
    source = "".join("".join(row) for row in zip_longest(*values, fillvalue=""))[:20]
    digest = hashlib.md5(source.encode(), usedforsecurity=False).hexdigest()
    tail = list(map(ord, digest[-6:]))
    mixed = [
        _mix(tail[i])
        ^ _six(tail[i])
        ^ _triple(tail[i])
        ^ _mix(tail[(i + 1) % 4])
        ^ _six(tail[(i + 2) % 4])
        ^ _triple(tail[(i + 3) % 4])
        for i in range(4)
    ]
    prefix = "".join(table[:-4][ord(char) % len(table[:-4])] for char in digest[:5])
    return prefix + f"{(sum(mixed) + sum(tail[4:])) % 100:02}"


def sign_params(path: str) -> dict[str, str]:
    stamp = int(time.time())
    nonce = secrets.token_hex(16).upper()
    return {"_time": str(stamp), "nonce": nonce, "hkey": hkey(path, stamp, nonce)}
