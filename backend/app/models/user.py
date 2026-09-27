import re
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Identity, Integer, String, Text, UniqueConstraint, func, text, true
from sqlalchemy.orm import Mapped, mapped_column, validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


MIN_PASSWORD_LENGTH = 12
_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    TECHNICIAN = "TECHNICIAN"


def normalize_username(value: str) -> str:
    """Store usernames as lowercase ASCII after trimming surrounding whitespace."""
    if not isinstance(value, str):
        raise ValueError("Username is required.")
    username = value.strip().lower()
    if not username or len(username) > 64 or not _USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username must use 1-64 lowercase letters, digits, dots, underscores, or hyphens.")
    return username


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        CheckConstraint("username ~ '^[a-z0-9][a-z0-9._-]*$'", name="ck_users_username_format"),
        CheckConstraint("role IN ('ADMIN', 'TECHNICIAN')", name="ck_users_role"),
        CheckConstraint("auth_version >= 0", name="ck_users_auth_version_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=true())
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @validates("username")
    def _normalize_username(self, _key: str, value: str) -> str:
        return normalize_username(value)

    @validates("full_name")
    def _validate_full_name(self, _key: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 160:
            raise ValueError("Full name must be 1-160 characters.")
        return value.strip()

    @validates("role")
    def _validate_role(self, _key: str, value: str) -> str:
        if value not in {role.value for role in UserRole}:
            raise ValueError("Invalid user role.")
        return str(value)

    def set_password(self, password: str) -> None:
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return isinstance(password, str) and bool(self.password_hash) and check_password_hash(
            self.password_hash, password
        )

    def __repr__(self) -> str:
        return f"<User id={self.id}>"
