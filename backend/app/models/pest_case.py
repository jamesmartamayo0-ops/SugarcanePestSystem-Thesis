import re
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.farm import MAX_AREA_HECTARES, normalize_area_hectares


class PestCaseStatus(StrEnum):
    REPORTED = "REPORTED"
    FOR_INSPECTION = "FOR_INSPECTION"


_ALLOWED_STATUSES = frozenset({status.value for status in PestCaseStatus})
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_pest_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Pest name must be 1-120 characters.")
    cleaned = _WHITESPACE_PATTERN.sub(" ", value.strip())
    if not cleaned or len(cleaned) > 120:
        raise ValueError("Pest name must be 1-120 characters.")
    return cleaned


def normalize_symptoms(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Symptoms must be at most 2000 characters.")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 2000:
        raise ValueError("Symptoms must be at most 2000 characters.")
    return cleaned


def normalize_observed_on(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError("Observation date must use YYYY-MM-DD format.")
    if isinstance(value, date):
        observed = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            observed = date.fromisoformat(cleaned)
        except ValueError:
            raise ValueError("Observation date must use YYYY-MM-DD format.") from None
    else:
        raise ValueError("Observation date must use YYYY-MM-DD format.")
    if observed > date.today():
        raise ValueError("Observation date cannot be in the future.")
    return observed


def normalize_reported_area(value: object) -> Decimal:
    try:
        return normalize_area_hectares(value)
    except ValueError as exc:
        raise ValueError(
            "Reported area must be greater than 0 and at most "
            f"{MAX_AREA_HECTARES} hectares, with at most 2 decimal places."
        ) from exc


class PestCase(db.Model):
    __tablename__ = "pest_cases"
    __table_args__ = (
        CheckConstraint("reported_area_hectares > 0", name="ck_pest_cases_area_positive"),
        CheckConstraint(
            "reported_area_hectares <= 10000", name="ck_pest_cases_area_max"
        ),
        CheckConstraint(
            "status IN ('REPORTED', 'FOR_INSPECTION')", name="ck_pest_cases_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    farm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    pest_name: Mapped[str] = mapped_column(String(120), nullable=False)
    symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reported_area_hectares: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=PestCaseStatus.REPORTED.value,
        server_default="REPORTED",
    )
    reported_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reported_at: Mapped[datetime] = mapped_column(
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

    # Plain (non-back-populated) references: later workflow phases and their
    # relationships can extend these without touching Farm/User mappings.
    farm: Mapped["Farm"] = relationship("Farm")
    reporter: Mapped["User"] = relationship("User")

    @validates("farm_id", "reported_by_user_id")
    def _validate_reference(self, key: str, value: int) -> int:
        if type(value) is not int or not 0 < value <= 2_147_483_647:
            if key == "farm_id":
                raise ValueError("Farm reference is invalid.")
            raise ValueError("Reporter reference is invalid.")
        return value

    @validates("pest_name")
    def _validate_pest_name(self, _key: str, value: str) -> str:
        return normalize_pest_name(value)

    @validates("symptoms")
    def _validate_symptoms(self, _key: str, value: str | None) -> str | None:
        return normalize_symptoms(value)

    @validates("observed_on")
    def _validate_observed_on(self, _key: str, value: date | str | None) -> date | None:
        return normalize_observed_on(value)

    @validates("reported_area_hectares")
    def _validate_reported_area(self, _key: str, value: object) -> Decimal:
        return normalize_reported_area(value)

    @validates("status")
    def _validate_status(self, _key: str, value: str) -> str:
        if value not in _ALLOWED_STATUSES:
            raise ValueError("Invalid pest case status.")
        return str(value)

    def __repr__(self) -> str:
        return f"<PestCase id={self.id}>"
