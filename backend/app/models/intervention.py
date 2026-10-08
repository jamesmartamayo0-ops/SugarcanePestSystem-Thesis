from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db

try:
    _MANILA_TZ = ZoneInfo("Asia/Manila")
except Exception:  # pragma: no cover - tzdata missing fallback keeps UTC+8 policy.
    _MANILA_TZ = timezone(timedelta(hours=8))


def manila_today() -> date:
    return datetime.now(_MANILA_TZ).date()


METHOD_CATEGORIES = frozenset({"CULTURAL", "MECHANICAL", "BIOLOGICAL", "CHEMICAL", "OTHER"})


def normalize_method_category(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Intervention category must be one of CULTURAL, MECHANICAL, BIOLOGICAL, CHEMICAL, OTHER.")
    cleaned = value.strip()
    if cleaned not in METHOD_CATEGORIES:
        raise ValueError("Intervention category must be one of CULTURAL, MECHANICAL, BIOLOGICAL, CHEMICAL, OTHER.")
    return cleaned


def normalize_method_description(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Intervention description must be 1-2000 characters.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Intervention description must not be blank.")
    if len(cleaned) > 2000:
        raise ValueError("Intervention description must be at most 2000 characters.")
    return cleaned


def normalize_completion_notes(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Completion notes must be 1-2000 characters.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Completion notes must not be blank.")
    if len(cleaned) > 2000:
        raise ValueError("Completion notes must be at most 2000 characters.")
    return cleaned


def _normalize_iso_date(value: date | str, field_label: str, allow_future: bool) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{field_label} must use YYYY-MM-DD format.")
    if isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{field_label} must use YYYY-MM-DD format.")
        try:
            parsed = date.fromisoformat(cleaned)
        except ValueError:
            raise ValueError(f"{field_label} must use YYYY-MM-DD format.") from None
    else:
        raise ValueError(f"{field_label} must use YYYY-MM-DD format.")
    if not allow_future and parsed > manila_today():
        raise ValueError(f"{field_label} cannot be in the future.")
    return parsed


def normalize_scheduled_for(value: date | str) -> date:
    return _normalize_iso_date(value, "Scheduled date", allow_future=True)


def normalize_follow_up_due_on(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        raise ValueError("Follow-up date must use YYYY-MM-DD format.")
    return _normalize_iso_date(value, "Follow-up date", allow_future=True)


def normalize_performed_on(value: date | str) -> date:
    return _normalize_iso_date(value, "Performed date", allow_future=False)


class Intervention(db.Model):
    __tablename__ = "interventions"
    __table_args__ = (
        CheckConstraint(
            "method_category IN ('CULTURAL', 'MECHANICAL', 'BIOLOGICAL', 'CHEMICAL', 'OTHER')",
            name="ck_interventions_method_category",
        ),
        CheckConstraint(
            "length(btrim(method_description)) > 0",
            name="ck_interventions_description_nonblank",
        ),
        CheckConstraint(
            "char_length(method_description) <= 2000",
            name="ck_interventions_description_max",
        ),
        CheckConstraint(
            "(completed_at IS NULL AND completed_by_user_id IS NULL "
            "AND performed_on IS NULL AND completion_notes IS NULL) "
            "OR (completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL "
            "AND performed_on IS NOT NULL AND completion_notes IS NOT NULL)",
            name="ck_interventions_completion_state",
        ),
        CheckConstraint(
            "completion_notes IS NULL OR length(btrim(completion_notes)) > 0",
            name="ck_interventions_notes_nonblank",
        ),
        CheckConstraint(
            "completion_notes IS NULL OR char_length(completion_notes) <= 2000",
            name="ck_interventions_notes_max",
        ),
        CheckConstraint(
            "completed_at IS NULL OR follow_up_due_on IS NOT NULL",
            name="ck_interventions_follow_up_required",
        ),
        CheckConstraint(
            "completed_at IS NULL OR follow_up_due_on >= performed_on",
            name="ck_interventions_follow_up_order",
        ),
        Index(
            "uq_interventions_pending_case",
            "pest_case_id",
            unique=True,
            postgresql_where=text("completed_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    pest_case_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pest_cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    method_category: Mapped[str] = mapped_column(String(16), nullable=False)
    method_description: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    assigned_to_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    performed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_due_on: Mapped[date | None] = mapped_column(
        Date, nullable=True, index=True
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
        DateTime(timezone=True), nullable=True, index=True
    )

    # Plain references: later workflow phases extend without touching existing mappings.
    pest_case: Mapped["PestCase"] = relationship("PestCase")
    assignee: Mapped["User"] = relationship("User", foreign_keys=[assigned_to_user_id])
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by_user_id])
    completer: Mapped["User | None"] = relationship(
        "User", foreign_keys=[completed_by_user_id]
    )

    @validates("pest_case_id", "assigned_to_user_id", "created_by_user_id")
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

    @validates("method_category")
    def _validate_method_category(self, _key: str, value: str) -> str:
        return normalize_method_category(value)

    @validates("method_description")
    def _validate_method_description(self, _key: str, value: str) -> str:
        return normalize_method_description(value)

    @validates("scheduled_for")
    def _validate_scheduled_for(self, _key: str, value: date | str) -> date:
        return normalize_scheduled_for(value)

    @validates("performed_on")
    def _validate_performed_on(self, _key: str, value: date | str | None) -> date | None:
        if value is None:
            return None
        return normalize_performed_on(value)

    @validates("completion_notes")
    def _validate_completion_notes(self, _key: str, value: str | None) -> str | None:
        return normalize_completion_notes(value)

    @validates("follow_up_due_on")
    def _validate_follow_up(self, _key: str, value: date | str | None) -> date | None:
        return normalize_follow_up_due_on(value)

    def __repr__(self) -> str:
        return f"<Intervention id={self.id}>"
