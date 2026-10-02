import re

from pydantic import BaseModel, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MAX_LENGTH = 255


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not value:
        raise ValueError("Email address is required.")
    if len(value) > EMAIL_MAX_LENGTH:
        raise ValueError(f"Email must be at most {EMAIL_MAX_LENGTH} characters.")
    if not EMAIL_PATTERN.match(value):
        raise ValueError("Enter a valid email address.")
    return value


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class RegisterRequest(BaseModel):
    """Body for POST /register. There is no role field, so the API cannot create admins."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    email: str
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password needs at least one letter and one number.")
        return value
