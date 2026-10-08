import re
from datetime import datetime, timezone

from sqlalchemy import DateTime, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db

_CONTACT_PATTERN = re.compile(r"^[0-9+\-\s()]{7,32}$")


def normalize_farmer_name(value: str) -> str:
    """Trim surrounding whitespace; names are stored as entered (no case folding)."""
    if not isinstance(value, str):
        raise ValueError("Full name must be 1-160 characters.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 160:
        raise ValueError("Full name must be 1-160 characters.")
    return cleaned


def normalize_barangay(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Barangay must be 1-120 characters.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 120:
        raise ValueError("Barangay must be 1-120 characters.")
    return cleaned


def normalize_contact_number(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Contact number must be 7-32 digits, spaces, or + - ( ) characters.")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 32 or _CONTACT_PATTERN.fullmatch(cleaned) is None:
        raise ValueError("Contact number must be 7-32 digits, spaces, or + - ( ) characters.")
    return cleaned


class Farmer(db.Model):
    __tablename__ = "farmers"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    barangay: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
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

    # No delete cascade: farm history must survive even if a farmer record
    # is ever retired. The database FK uses ON DELETE RESTRICT.
    farms: Mapped[list["Farm"]] = relationship(
        "Farm",
        back_populates="farmer",
        cascade="save-update, merge",
        passive_deletes=True,
    )

    @validates("full_name")
    def _validate_full_name(self, _key: str, value: str) -> str:
        return normalize_farmer_name(value)

    @validates("barangay")
    def _validate_barangay(self, _key: str, value: str) -> str:
        return normalize_barangay(value)

    @validates("contact_number")
    def _validate_contact_number(self, _key: str, value: str | None) -> str | None:
        return normalize_contact_number(value)

    def __repr__(self) -> str:
        return f"<Farmer id={self.id}>"
