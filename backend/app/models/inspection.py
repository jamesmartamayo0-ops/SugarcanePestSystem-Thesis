from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.farm import MAX_AREA_HECTARES

try:
    _MANILA_TZ = ZoneInfo("Asia/Manila")
except Exception:  # pragma: no cover - tzdata missing fallback keeps UTC+8 policy.
    _MANILA_TZ = timezone(timedelta(hours=8))


def manila_today() -> date:
    return datetime.now(_MANILA_TZ).date()


def normalize_scheduled_for(value: date | str) -> date:
    if isinstance(value, datetime):
        raise ValueError("Scheduled date must use YYYY-MM-DD format.")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("Scheduled date must use YYYY-MM-DD format.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Scheduled date must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError("Scheduled date must use YYYY-MM-DD format.") from None


def normalize_inspected_on(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError("Inspection date must use YYYY-MM-DD format.")
    if isinstance(value, date):
        inspected = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Inspection date must use YYYY-MM-DD format.")
        try:
            inspected = date.fromisoformat(cleaned)
        except ValueError:
            raise ValueError("Inspection date must use YYYY-MM-DD format.") from None
    else:
        raise ValueError("Inspection date must use YYYY-MM-DD format.")
    if inspected > manila_today():
        raise ValueError("Inspection date cannot be in the future.")
    return inspected


def normalize_findings(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Findings must be 1-2000 characters.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Findings must not be blank.")
    if len(cleaned) > 2000:
        raise ValueError("Findings must be at most 2000 characters.")
    return cleaned


def normalize_validated_area(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(
            "Validated area must be between 0 and 10000 hectares, "
            "with at most 2 decimal places."
        )
    try:
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("invalid")
            area = Decimal(str(value))
        elif isinstance(value, Decimal):
            area = value
        elif isinstance(value, int):
            area = Decimal(value)
        elif isinstance(value, str):
            cleaned = value.strip()
            if not cleaned or len(cleaned) > 32:
                raise ValueError("invalid")
            area = Decimal(cleaned)
        else:
            raise ValueError("invalid")
    except (InvalidOperation, ValueError, ArithmeticError):
        raise ValueError(
            "Validated area must be between 0 and 10000 hectares, "
            "with at most 2 decimal places."
        ) from None
    if area < 0 or area > MAX_AREA_HECTARES:
        raise ValueError(
            "Validated area must be between 0 and 10000 hectares, "
            "with at most 2 decimal places."
        )
    if area.as_tuple().exponent < -2:
        raise ValueError("Validated area may have at most 2 decimal places.")
    return area.quantize(Decimal("0.01"))


class Inspection(db.Model):
    __tablename__ = "inspections"
    __table_args__ = (
        UniqueConstraint("pest_case_id", name="uq_inspections_pest_case_id"),
        CheckConstraint(
            "validated_area_hectares IS NULL OR "
            "(validated_area_hectares >= 0 AND validated_area_hectares <= 10000)",
            name="ck_inspections_validated_range",
        ),
        CheckConstraint(
            "(completed_at IS NULL AND completed_by_user_id IS NULL "
            "AND inspected_on IS NULL AND findings IS NULL "
            "AND pest_confirmed IS NULL AND validated_area_hectares IS NULL) "
            "OR (completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL "
            "AND inspected_on IS NOT NULL AND findings IS NOT NULL "
            "AND pest_confirmed IS NOT NULL AND validated_area_hectares IS NOT NULL)",
            name="ck_inspections_completion_state",
        ),
        CheckConstraint(
            "findings IS NULL OR length(btrim(findings)) > 0",
            name="ck_inspections_findings_nonblank",
        ),
        CheckConstraint(
            "findings IS NULL OR char_length(findings) <= 2000",
            name="ck_inspections_findings_max",
        ),
        CheckConstraint(
            "(pest_confirmed IS NULL AND validated_area_hectares IS NULL) "
            "OR (pest_confirmed = TRUE AND validated_area_hectares > 0) "
            "OR (pest_confirmed = FALSE AND validated_area_hectares = 0)",
            name="ck_inspections_confirmed_area",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    pest_case_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pest_cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)
    assigned_to_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scheduled_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inspected_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    pest_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validated_area_hectares: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    completed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Plain references: workflow phases extend without touching Farm/User mappings.
    pest_case: Mapped["PestCase"] = relationship("PestCase")
    assignee: Mapped["User"] = relationship("User", foreign_keys=[assigned_to_user_id])
    scheduler: Mapped["User"] = relationship("User", foreign_keys=[scheduled_by_user_id])
    completer: Mapped["User | None"] = relationship(
        "User", foreign_keys=[completed_by_user_id]
    )

    @validates("pest_case_id", "assigned_to_user_id", "scheduled_by_user_id")
    def _validate_required_reference(self, key: str, value: int) -> int:
        if type(value) is not int or not 0 < value <= 2_147_483_647:
            if key == "pest_case_id":
                raise ValueError("Pest case reference is invalid.")
            raise ValueError("Technician reference is invalid.")
        return value

    @validates("completed_by_user_id")
    def _validate_optional_reference(self, _key: str, value: int | None) -> int | None:
        if value is None:
            return None
        if type(value) is not int or not 0 < value <= 2_147_483_647:
            raise ValueError("Technician reference is invalid.")
        return value

    @validates("scheduled_for")
    def _validate_scheduled_for(self, _key: str, value: date | str) -> date:
        return normalize_scheduled_for(value)

    @validates("inspected_on")
    def _validate_inspected_on(self, _key: str, value: date | str | None) -> date | None:
        return normalize_inspected_on(value)

    @validates("findings")
    def _validate_findings(self, _key: str, value: str | None) -> str | None:
        return normalize_findings(value)

    @validates("validated_area_hectares")
    def _validate_validated_area(self, _key: str, value: object) -> Decimal | None:
        return normalize_validated_area(value)

    @validates("pest_confirmed")
    def _validate_pest_confirmed(self, _key: str, value: bool | None) -> bool | None:
        if value is None:
            return None
        if type(value) is not bool:
            raise ValueError("Pest confirmation must be true or false.")
        return value

    def __repr__(self) -> str:
        return f"<Inspection id={self.id}>"
