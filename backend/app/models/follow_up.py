from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
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


class FollowUpOutcome(StrEnum):
    RESOLVED = "RESOLVED"
    REINTERVENTION_REQUIRED = "REINTERVENTION_REQUIRED"


_FOLLOW_UP_OUTCOMES = frozenset({outcome.value for outcome in FollowUpOutcome})


def normalize_follow_up_observed_on(value: date | str) -> date:
    if isinstance(value, datetime):
        raise ValueError("Observed date must use YYYY-MM-DD format.")
    if isinstance(value, date):
        observed = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Observed date must use YYYY-MM-DD format.")
        try:
            observed = date.fromisoformat(cleaned)
        except ValueError:
            raise ValueError("Observed date must use YYYY-MM-DD format.") from None
    else:
        raise ValueError("Observed date must use YYYY-MM-DD format.")
    if observed > manila_today():
        raise ValueError("Observed date cannot be in the future.")
    return observed


def normalize_pest_observed(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("Pest observation must be true or false.")
    return value


def normalize_observed_area(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(
            "Observed area must be between 0 and 10000 hectares, "
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
            "Observed area must be between 0 and 10000 hectares, "
            "with at most 2 decimal places."
        ) from None
    if area < 0 or area > MAX_AREA_HECTARES:
        raise ValueError(
            "Observed area must be between 0 and 10000 hectares, "
            "with at most 2 decimal places."
        )
    if area.as_tuple().exponent < -2:
        raise ValueError("Observed area may have at most 2 decimal places.")
    return area.quantize(Decimal("0.01"))


def normalize_assessment_notes(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Assessment notes must be 1-2000 characters.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Assessment notes must not be blank.")
    if len(cleaned) > 2000:
        raise ValueError("Assessment notes must be at most 2000 characters.")
    return cleaned


def normalize_follow_up_outcome(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Follow-up outcome must be RESOLVED or REINTERVENTION_REQUIRED.")
    cleaned = value.strip()
    if cleaned not in _FOLLOW_UP_OUTCOMES:
        raise ValueError("Follow-up outcome must be RESOLVED or REINTERVENTION_REQUIRED.")
    return cleaned


class FollowUp(db.Model):
    __tablename__ = "follow_ups"
    __table_args__ = (
        UniqueConstraint("intervention_id", name="uq_follow_ups_intervention_id"),
        CheckConstraint(
            "outcome IN ('RESOLVED', 'REINTERVENTION_REQUIRED')",
            name="ck_follow_ups_outcome",
        ),
        CheckConstraint(
            "length(btrim(assessment_notes)) > 0",
            name="ck_follow_ups_notes_nonblank",
        ),
        CheckConstraint(
            "char_length(assessment_notes) <= 2000",
            name="ck_follow_ups_notes_max",
        ),
        CheckConstraint(
            "observed_affected_area_hectares IS NULL OR "
            "(observed_affected_area_hectares >= 0 AND observed_affected_area_hectares <= 10000)",
            name="ck_follow_ups_area_range",
        ),
        Index("ix_follow_ups_observed_on", "observed_on"),
        Index("ix_follow_ups_outcome", "outcome"),
        Index("ix_follow_ups_recorded_by_user_id", "recorded_by_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    intervention_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("interventions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    pest_observed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_affected_area_hectares: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    assessment_notes: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    recorded_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
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

    intervention: Mapped["Intervention"] = relationship("Intervention")
    recorder: Mapped["User"] = relationship("User")

    @validates("intervention_id", "recorded_by_user_id")
    def _validate_reference(self, key: str, value: int) -> int:
        if type(value) is not int or not 0 < value <= 2_147_483_647:
            if key == "intervention_id":
                raise ValueError("Intervention reference is invalid.")
            raise ValueError("Recorder reference is invalid.")
        return value

    @validates("observed_on")
    def _validate_observed_on(self, _key: str, value: date | str) -> date:
        return normalize_follow_up_observed_on(value)

    @validates("pest_observed")
    def _validate_pest_observed(self, _key: str, value: object) -> bool:
        return normalize_pest_observed(value)

    @validates("observed_affected_area_hectares")
    def _validate_observed_area(self, _key: str, value: object) -> Decimal | None:
        return normalize_observed_area(value)

    @validates("assessment_notes")
    def _validate_notes(self, _key: str, value: str) -> str:
        return normalize_assessment_notes(value)

    @validates("outcome")
    def _validate_outcome(self, _key: str, value: str) -> str:
        return normalize_follow_up_outcome(value)

    def __repr__(self) -> str:
        return f"<FollowUp id={self.id}>"
