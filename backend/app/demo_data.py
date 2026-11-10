"""Deterministic synthetic demo dataset for the thesis demo.

All names are clearly fictional. Repeated execution is safe: if the demo
marker farmer already exists, seeding is refused without changes.
"""

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.extensions import db
from app.models import Farm, Farmer, FollowUp, Inspection, Intervention, PestCase, User, UserRole

ALLOWED_DATABASE = "sugarcane_pest_test"
FORBIDDEN_DATABASE = "sugarcane_pest_db"
DEMO_FARMER_MARKER = "Demo Farmer 01 (Synthetic)"

try:
    _MANILA_TZ = ZoneInfo("Asia/Manila")
except Exception:
    _MANILA_TZ = timezone(timedelta(hours=8))


def manila_today() -> date:
    return datetime.now(_MANILA_TZ).date()


def _require_demo_database() -> None:
    configured = os.environ.get("DB_NAME", "")
    if configured != ALLOWED_DATABASE:
        raise RuntimeError(
            f"Refusing to seed: DB_NAME must be {ALLOWED_DATABASE} (got {configured!r})."
        )


def _verify_live_database() -> None:
    name = db.session.execute(text("SELECT current_database()")).scalar_one()
    if name != ALLOWED_DATABASE:
        raise RuntimeError(f"Refusing to seed: live database is {name!r}.")
    if name == FORBIDDEN_DATABASE:
        raise RuntimeError("Refusing to seed the thesis database.")


def demo_already_seeded() -> bool:
    return (
        db.session.scalar(
            select(Farmer.id).where(Farmer.full_name == DEMO_FARMER_MARKER).limit(1)
        )
        is not None
    )


def _get_or_create_demo_users():
    admin = db.session.scalar(select(User).where(User.role == UserRole.ADMIN.value).limit(1))
    tech = db.session.scalar(
        select(User)
        .where(User.role == UserRole.TECHNICIAN.value, User.is_active.is_(True))
        .order_by(User.id)
        .limit(1)
    )
    if tech is None:
        tech = User(username="demo.tech", full_name="Demo Technician (Synthetic)", role="TECHNICIAN", is_active=True)
        tech.set_password("Demo-Technician-Password-123!")
        db.session.add(tech)
        db.session.flush()
    return admin, tech


DEMO_FARMERS = [
    ("Demo Farmer 01 (Synthetic)", "Bunao"),
    ("Demo Farmer 02 (Synthetic)", "Calindagan"),
    ("Demo Farmer 03 (Synthetic)", "Taclobo"),
    ("Demo Farmer 04 (Synthetic)", "Bunao"),
    ("Demo Farmer 05 (Synthetic)", "San Jose"),
    ("Demo Farmer 06 (Synthetic)", "Malabo"),
    ("Demo Farmer 07 (Synthetic)", "Bunao"),
    ("Demo Farmer 08 (Synthetic)", "Calindagan"),
    ("Demo Farmer 09 (Synthetic)", "Taclobo"),
    ("Demo Farmer 10 (Synthetic)", "San Jose"),
]

DEMO_FARMS = [
    # (farmer_index, plot, barangay, area)
    (0, "Demo Plot A01", "Bunao", "2.00"),
    (0, "Demo Plot A02", "Bunao", "1.50"),
    (1, "Demo Plot B01", "Calindagan", "3.00"),
    (2, "Demo Plot C01", "Taclobo", "2.50"),
    (3, "Demo Plot D01", "Bunao", "4.00"),
    (4, "Demo Plot E01", "San Jose", "1.00"),
    (5, "Demo Plot F01", "Malabo", "2.00"),
    (6, "Demo Plot G01", "Bunao", "3.50"),
    (7, "Demo Plot H01", "Calindagan", "2.00"),
    (8, "Demo Plot I01", "Taclobo", "1.25"),
    (9, "Demo Plot J01", "San Jose", "2.75"),
    (9, "Demo Plot J02", "San Jose", "1.75"),
]


def seed_demo_data() -> dict:
    """Seed the deterministic demo dataset. Returns counts."""
    _require_demo_database()
    _verify_live_database()
    if demo_already_seeded():
        return {"seeded": False, "reason": "Demo data already present; refusing duplicate seeding."}

    today = manila_today()
    admin, tech = _get_or_create_demo_users()
    reporter_id = admin.id if admin is not None else tech.id

    farmers = []
    for name, barangay in DEMO_FARMERS:
        farmer = Farmer(full_name=name, barangay=barangay)
        db.session.add(farmer)
        farmers.append(farmer)
    db.session.flush()

    farms = []
    for farmer_idx, plot, barangay, area in DEMO_FARMS:
        farm = Farm(
            farmer_id=farmers[farmer_idx].id,
            plot_identifier=plot,
            barangay=barangay,
            area_hectares=area,
        )
        db.session.add(farm)
        farms.append(farm)
    db.session.flush()

    def new_case(farm_idx, pest, status, symptoms="Demo symptoms (synthetic)"):
        case = PestCase(
            farm_id=farms[farm_idx].id,
            pest_name=pest,
            symptoms=symptoms,
            observed_on=today - timedelta(days=20),
            reported_area_hectares="1.00",
            status=status,
            reported_by_user_id=reporter_id,
        )
        db.session.add(case)
        return case

    # Cases 1-4: early pipeline.
    c_reported = new_case(0, "Demo Stem Borer (Synthetic)", "REPORTED")
    c_for_inspection = new_case(1, "Demo White Grub (Synthetic)", "FOR_INSPECTION")
    c_scheduled = new_case(2, "Demo Armyworm (Synthetic)", "INSPECTION_SCHEDULED")
    c_validated = new_case(3, "Demo Termite (Synthetic)", "FIELD_VALIDATED")
    c_not_confirmed = new_case(4, "Demo Mole Cricket (Synthetic)", "NOT_CONFIRMED")
    db.session.flush()

    # Inspections for scheduled/validated/not-confirmed. Completed demo
    # inspections keep scheduled_for <= inspected_on <= Manila today.
    def schedule_and_record(case, confirmed, area, inspected_offset=10):
        inspection = Inspection(
            pest_case_id=case.id,
            scheduled_for=today - timedelta(days=12),
            assigned_to_user_id=tech.id,
            scheduled_by_user_id=reporter_id,
        )
        db.session.add(inspection)
        db.session.flush()
        inspection.inspected_on = today - timedelta(days=inspected_offset)
        inspection.findings = "Demo field findings (synthetic)"
        inspection.pest_confirmed = confirmed
        inspection.confirmed_pest_name = case.pest_name if confirmed else None
        inspection.validated_area_hectares = Decimal(area)
        inspection.completed_by_user_id = tech.id
        inspection.completed_at = datetime.now(timezone.utc)
        try:
            inspection.completer = tech
        except Exception:
            pass
        return inspection

    schedule_only = Inspection(
        pest_case_id=c_scheduled.id,
        scheduled_for=today + timedelta(days=3),
        assigned_to_user_id=tech.id,
        scheduled_by_user_id=reporter_id,
    )
    db.session.add(schedule_only)
    schedule_and_record(c_validated, True, "1.00")
    schedule_and_record(c_not_confirmed, False, "0.00")

    # UNDER_INTERVENTION with pending intervention.
    c_under = new_case(5, "Demo Cutworm (Synthetic)", "UNDER_INTERVENTION")
    db.session.flush()
    pending = Intervention(
        pest_case_id=c_under.id,
        method_category="CULTURAL",
        method_description="Demo manual removal (synthetic)",
        scheduled_for=today - timedelta(days=5),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today + timedelta(days=7),
    )
    db.session.add(pending)

    # FOLLOW_UP_DUE upcoming.
    c_due_up = new_case(6, "Demo Leafhopper (Synthetic)", "FOLLOW_UP_DUE")
    db.session.flush()
    up = Intervention(
        pest_case_id=c_due_up.id,
        method_category="MECHANICAL",
        method_description="Demo trapping (synthetic)",
        scheduled_for=today - timedelta(days=6),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today + timedelta(days=7),
    )
    db.session.add(up)
    db.session.flush()
    up.performed_on = today - timedelta(days=1)
    up.completion_notes = "Demo completed (synthetic)"
    up.completed_by_user_id = tech.id
    up.completed_at = datetime.now(timezone.utc)

    # FOLLOW_UP_DUE overdue.
    c_due_over = new_case(7, "Demo Aphid (Synthetic)", "FOLLOW_UP_DUE")
    db.session.flush()
    over = Intervention(
        pest_case_id=c_due_over.id,
        method_category="CULTURAL",
        method_description="Demo sanitation (synthetic)",
        scheduled_for=today - timedelta(days=8),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today - timedelta(days=1),
    )
    db.session.add(over)
    db.session.flush()
    over.performed_on = today - timedelta(days=3)
    over.completion_notes = "Demo completed (synthetic)"
    over.completed_by_user_id = tech.id
    over.completed_at = datetime.now(timezone.utc)

    # REINTERVENTION_REQUIRED.
    c_re = new_case(8, "Demo Rat (Synthetic)", "REINTERVENTION_REQUIRED")
    db.session.flush()
    re_int = Intervention(
        pest_case_id=c_re.id,
        method_category="BIOLOGICAL",
        method_description="Demo biological control (synthetic)",
        scheduled_for=today - timedelta(days=9),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today - timedelta(days=2),
    )
    db.session.add(re_int)
    db.session.flush()
    re_int.performed_on = today - timedelta(days=5)
    re_int.completion_notes = "Demo completed (synthetic)"
    re_int.completed_by_user_id = tech.id
    re_int.completed_at = datetime.now(timezone.utc)
    db.session.flush()
    db.session.add(
        FollowUp(
            intervention_id=re_int.id,
            observed_on=today - timedelta(days=1),
            pest_observed=True,
            observed_affected_area_hectares=Decimal("0.50"),
            assessment_notes="Demo reassessment: further work needed (synthetic)",
            outcome="REINTERVENTION_REQUIRED",
            recorded_by_user_id=tech.id,
        )
    )

    # CLOSED resolved first intervention.
    c_closed = new_case(9, "Demo Stalk Borer (Synthetic)", "CLOSED")
    db.session.flush()
    cl_int = Intervention(
        pest_case_id=c_closed.id,
        method_category="OTHER",
        method_description="Demo cleanup (synthetic)",
        scheduled_for=today - timedelta(days=9),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today - timedelta(days=2),
    )
    db.session.add(cl_int)
    db.session.flush()
    cl_int.performed_on = today - timedelta(days=5)
    cl_int.completion_notes = "Demo completed (synthetic)"
    cl_int.completed_by_user_id = tech.id
    cl_int.completed_at = datetime.now(timezone.utc)
    db.session.flush()
    db.session.add(
        FollowUp(
            intervention_id=cl_int.id,
            observed_on=today - timedelta(days=1),
            pest_observed=False,
            observed_affected_area_hectares=Decimal("0.00"),
            assessment_notes="Demo reassessment: resolved (synthetic)",
            outcome="RESOLVED",
            recorded_by_user_id=tech.id,
        )
    )

    # Two-cycle CLOSED: FIELD_VALIDATED -> ... -> CLOSED with 2+2 records.
    c_two = new_case(10, "Demo Two-Cycle Borer (Synthetic)", "CLOSED")
    db.session.flush()
    first = Intervention(
        pest_case_id=c_two.id,
        method_category="CULTURAL",
        method_description="Demo first cycle (synthetic)",
        scheduled_for=today - timedelta(days=14),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today - timedelta(days=10),
    )
    db.session.add(first)
    db.session.flush()
    first.performed_on = today - timedelta(days=12)
    first.completion_notes = "Demo first completed (synthetic)"
    first.completed_by_user_id = tech.id
    first.completed_at = datetime.now(timezone.utc)
    db.session.flush()
    db.session.add(
        FollowUp(
            intervention_id=first.id,
            observed_on=today - timedelta(days=9),
            pest_observed=True,
            observed_affected_area_hectares=Decimal("0.75"),
            assessment_notes="Demo first reassessment (synthetic)",
            outcome="REINTERVENTION_REQUIRED",
            recorded_by_user_id=tech.id,
        )
    )
    db.session.flush()
    second = Intervention(
        pest_case_id=c_two.id,
        method_category="MECHANICAL",
        method_description="Demo second cycle (synthetic)",
        scheduled_for=today - timedelta(days=8),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today - timedelta(days=2),
    )
    db.session.add(second)
    db.session.flush()
    second.performed_on = today - timedelta(days=5)
    second.completion_notes = "Demo second completed (synthetic)"
    second.completed_by_user_id = tech.id
    second.completed_at = datetime.now(timezone.utc)
    db.session.flush()
    db.session.add(
        FollowUp(
            intervention_id=second.id,
            observed_on=today - timedelta(days=1),
            pest_observed=False,
            observed_affected_area_hectares=Decimal("0.00"),
            assessment_notes="Demo second reassessment resolved (synthetic)",
            outcome="RESOLVED",
            recorded_by_user_id=tech.id,
        )
    )

    # Extra pipeline variety to reach 15-25 cases.
    new_case(11, "Demo Extra Borer A (Synthetic)", "REPORTED")
    extra_for = new_case(0, "Demo Extra Borer B (Synthetic)", "FOR_INSPECTION")
    extra_val = new_case(1, "Demo Extra Borer C (Synthetic)", "FIELD_VALIDATED")
    db.session.flush()
    schedule_and_record(extra_val, True, "0.50")
    extra_closed = new_case(2, "Demo Extra Borer D (Synthetic)", "CLOSED")
    db.session.flush()
    ec = Intervention(
        pest_case_id=extra_closed.id,
        method_category="CULTURAL",
        method_description="Demo extra closure (synthetic)",
        scheduled_for=today - timedelta(days=9),
        assigned_to_user_id=tech.id,
        created_by_user_id=reporter_id,
        follow_up_due_on=today - timedelta(days=2),
    )
    db.session.add(ec)
    db.session.flush()
    ec.performed_on = today - timedelta(days=5)
    ec.completion_notes = "Demo completed (synthetic)"
    ec.completed_by_user_id = tech.id
    ec.completed_at = datetime.now(timezone.utc)
    db.session.flush()
    db.session.add(
        FollowUp(
            intervention_id=ec.id,
            observed_on=today - timedelta(days=1),
            pest_observed=False,
            observed_affected_area_hectares=Decimal("0.10"),
            assessment_notes="Demo extra resolved (synthetic)",
            outcome="RESOLVED",
            recorded_by_user_id=tech.id,
        )
    )

    db.session.commit()
    return {
        "seeded": True,
        "farmers": len(DEMO_FARMERS),
        "farms": len(DEMO_FARMS),
        "note": "Deterministic synthetic demo data. Re-running refuses duplicates.",
    }
