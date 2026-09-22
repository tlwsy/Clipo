# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.schemas.settings import LlmUpdate

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64)]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]


class LoginRequest(BaseModel):
    username: Username
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        if not all(character.isalnum() or character in "_-" for character in value):
            raise ValueError("用户名只能包含文字、数字、下划线和短横线")
        return value.casefold()


class RegisterRequest(LoginRequest):
    password: Password
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class SetupRequest(RegisterRequest):
    llm: LlmUpdate | None = None


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, StringConstraints(max_length=256)] | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_admin: bool


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserResponse


class TokenRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class TokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None


class IssuedTokenResponse(TokenResponse):
    token: str


class ValidationField(BaseModel):
    field: str
    type: str
    message: str


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    fields: list[ValidationField] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: ErrorDetail = Field(default_factory=ErrorDetail)


class ErrorResponse(BaseModel):
    error: ErrorBody
