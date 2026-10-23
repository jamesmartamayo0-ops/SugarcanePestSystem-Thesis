from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Farmer,
    Farm,
    FollowUp,
    Inspection,
    Intervention,
    PestCase,
    PestCaseStatus,
)
from app.models.intervention import manila_today


ACTIVE_CASE_PRIORITY = {
    PestCaseStatus.REPORTED.value: 1,
    PestCaseStatus.FOR_INSPECTION.value: 2,
    PestCaseStatus.INSPECTION_SCHEDULED.value: 3,
    PestCaseStatus.FIELD_VALIDATED.value: 4,
    PestCaseStatus.UNDER_INTERVENTION.value: 5,
    PestCaseStatus.FOLLOW_UP_DUE.value: 6,
    PestCaseStatus.REINTERVENTION_REQUIRED.value: 7,
}
ACTIVE_CASE_STATUSES = frozenset(ACTIVE_CASE_PRIORITY)
TERMINAL_CASE_STATUSES = frozenset(
    {PestCaseStatus.CLOSED.value, PestCaseStatus.NOT_CONFIRMED.value}
)
ATTENTION_CASE_STATUSES = frozenset(
    {
        PestCaseStatus.FOR_INSPECTION.value,
        PestCaseStatus.FIELD_VALIDATED.value,
        PestCaseStatus.REINTERVENTION_REQUIRED.value,
    }
)
REGISTERED_NO_CASE = "REGISTERED_NO_CASE"


def _number(value: Decimal | int | float | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _farm_rows_statement():
    return (
        select(
            Farm.id.label("farm_id"),
            Farm.plot_identifier,
            Farm.barangay,
            Farm.area_hectares,
            Farm.latitude,
            Farm.longitude,
            Farmer.id.label("farmer_id"),
            Farmer.full_name.label("farmer_full_name"),
        )
        .join(Farmer, Farmer.id == Farm.farmer_id)
        .order_by(Farm.id)
    )


def _case_rows_statement():
    return (
        select(
            PestCase.id.label("case_id"),
            PestCase.farm_id,
            PestCase.pest_name,
            PestCase.status,
            PestCase.reported_area_hectares,
            PestCase.updated_at,
            Inspection.validated_area_hectares,
            Inspection.completed_at.label("inspection_completed_at"),
        )
        .outerjoin(Inspection, Inspection.pest_case_id == PestCase.id)
        .order_by(PestCase.farm_id, PestCase.id)
    )


def _overdue_follow_up_case_ids_statement():
    return (
        select(PestCase.id)
        .join(Intervention, Intervention.pest_case_id == PestCase.id)
        .outerjoin(FollowUp, FollowUp.intervention_id == Intervention.id)
        .where(
            Intervention.completed_at.is_not(None),
            PestCase.status == PestCaseStatus.FOLLOW_UP_DUE.value,
            FollowUp.id.is_(None),
            Intervention.follow_up_due_on.is_not(None),
            Intervention.follow_up_due_on < manila_today(),
        )
        .distinct()
    )


def _selected_case(case_rows: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    active = [row for row in case_rows if row["status"] in ACTIVE_CASE_STATUSES]
    if active:
        return max(
            active,
            key=lambda row: (
                ACTIVE_CASE_PRIORITY[row["status"]],
                row["updated_at"],
                row["case_id"],
            ),
        )

    terminal = [row for row in case_rows if row["status"] in TERMINAL_CASE_STATUSES]
    if terminal:
        return max(terminal, key=lambda row: (row["updated_at"], row["case_id"]))
    return None


def _case_payload(case_row: Mapping[str, Any]) -> dict:
    validated_area = (
        case_row["validated_area_hectares"]
        if case_row["inspection_completed_at"] is not None
        else None
    )
    return {
        "id": case_row["case_id"],
        "pest_name": case_row["pest_name"],
        "status": case_row["status"],
        "reported_area_hectares": _number(case_row["reported_area_hectares"]),
        "validated_area_hectares": _number(validated_area),
        "updated_at": (
            case_row["updated_at"].isoformat()
            if case_row["updated_at"] is not None
            else None
        ),
    }


def build_farm_map_projection(
    farm_rows: Iterable[Mapping[str, Any]],
    case_rows: Iterable[Mapping[str, Any]],
    overdue_follow_up_case_ids: Iterable[int],
) -> dict:
    farms = list(farm_rows)
    cases = list(case_rows)
    overdue_ids = set(overdue_follow_up_case_ids)
    attention_ids = {
        row["case_id"]
        for row in cases
        if row["status"] in ATTENTION_CASE_STATUSES
        or (
            row["status"] == PestCaseStatus.FOLLOW_UP_DUE.value
            and row["case_id"] in overdue_ids
        )
    }

    cases_by_farm: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in cases:
        cases_by_farm[row["farm_id"]].append(row)

    mapped_farms = 0
    projected_farms = []
    for farm in farms:
        farm_cases = cases_by_farm.get(farm["farm_id"], [])
        selected = _selected_case(farm_cases)
        mapped = farm["latitude"] is not None and farm["longitude"] is not None
        if mapped:
            mapped_farms += 1
        projected_farms.append(
            {
                "id": farm["farm_id"],
                "plot_identifier": farm["plot_identifier"],
                "farmer": {
                    "id": farm["farmer_id"],
                    "full_name": farm["farmer_full_name"],
                },
                "barangay": farm["barangay"],
                "area_hectares": _number(farm["area_hectares"]),
                "location": (
                    {
                        "latitude": _number(farm["latitude"]),
                        "longitude": _number(farm["longitude"]),
                    }
                    if mapped
                    else None
                ),
                "marker_state": selected["status"] if selected else REGISTERED_NO_CASE,
                "has_active_case": any(
                    row["status"] in ACTIVE_CASE_STATUSES for row in farm_cases
                ),
                "needs_attention": any(
                    row["case_id"] in attention_ids for row in farm_cases
                ),
                "case": _case_payload(selected) if selected else None,
            }
        )

    return {
        "summary": {
            "mapped_farms": mapped_farms,
            "unmapped_farms": len(farms) - mapped_farms,
            "active_cases": sum(
                row["status"] in ACTIVE_CASE_STATUSES for row in cases
            ),
            "needs_attention_cases": len(attention_ids),
        },
        "farms": projected_farms,
    }


def load_farm_map_projection() -> dict:
    """Load the projection with three set-based queries, independent of row count."""
    farm_rows = db.session.execute(_farm_rows_statement()).mappings().all()
    case_rows = db.session.execute(_case_rows_statement()).mappings().all()
    overdue_ids = db.session.scalars(_overdue_follow_up_case_ids_statement()).all()
    return build_farm_map_projection(farm_rows, case_rows, overdue_ids)
