# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from app.extractors.base import ExtractionError


class UnsafeURL(ExtractionError):
    def __init__(self):
        super().__init__(
            "仅支持公开网页的 HTTP(S) 链接，请检查地址，勿使用内网地址或账号密码", False
        )


def normalize_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        if (
            len(value) > 4096
            or any(ord(char) < 33 for char in value.strip())
            or "\\" in value
            or parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 80, 443)
        ):
            raise UnsafeURL()
        hostname = parts.hostname.encode("idna").decode().lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise UnsafeURL()
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            if not address.is_global or address.is_multicast:
                raise UnsafeURL()
        host = f"[{hostname}]" if ":" in hostname else hostname
        port = parts.port
        if port and port != (443 if parts.scheme == "https" else 80):
            host += f":{port}"
        return urlunsplit((parts.scheme, host, parts.path or "/", parts.query, ""))
    except (ValueError, UnicodeError) as exc:
        raise UnsafeURL() from exc


def public_addresses(url: str) -> list[str]:
    parts = urlsplit(normalize_url(url))
    try:
        records = socket.getaddrinfo(
            parts.hostname,
            parts.port or (443 if parts.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ExtractionError("无法解析网页域名，请检查链接或稍后重试") from exc
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses:
        raise ExtractionError("无法解析网页域名，请检查链接或稍后重试")
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global or address.is_multicast:
            raise UnsafeURL()
    return addresses
