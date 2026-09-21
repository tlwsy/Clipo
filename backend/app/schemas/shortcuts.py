from datetime import datetime
from ipaddress import ip_address
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
)

from app.schemas.auth import TokenRequest


class ShortcutInfo(BaseModel):
    shortcut_name: str = "保存到 Clipo"
    protocol_version: Literal[1] = 1
    install_url: str | None
    template_url: str = "/api/v1/shortcuts/template"


class PairingRequest(TokenRequest):
    model_config = ConfigDict(extra="forbid")
    server_url: str = Field(max_length=2048)

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        url = TypeAdapter(AnyHttpUrl).validate_python(value)
        if (
            url.username
            or url.password
            or url.query is not None
            or url.fragment is not None
            or url.path not in (None, "/")
        ):
            raise ValueError("服务器地址只能包含协议、主机和端口")
        if url.scheme == "http" and url.host != "localhost":
            try:
                address = ip_address((url.host or "").strip("[]"))
            except ValueError as exc:
                raise ValueError("公网服务器需要 HTTPS，HTTP 仅供本机和局域网测试") from exc
            if (
                not (address.is_private or address.is_loopback)
                or address.is_unspecified
                or address.is_multicast
            ):
                raise ValueError("公网服务器需要 HTTPS，HTTP 仅供本机和局域网测试")
        return str(url).rstrip("/")


class PairingStatus(BaseModel):
    id: str
    name: str
    expires_at: datetime
    status: Literal["pending", "expired", "claimed", "revoked"]
    token_id: int | None


class IssuedPairing(PairingStatus):
    setup_input: str
    launch_url: str


class ConsumePairing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(min_length=46, max_length=46)


class ShortcutConfiguration(BaseModel):
    version: Literal[1] = 1
    server_url: str
    token: str
    token_id: int
