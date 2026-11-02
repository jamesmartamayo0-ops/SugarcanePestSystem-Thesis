"""Role-based record visibility.

ADMIN accounts retain office-wide visibility. TECHNICIAN accounts only see
operational records connected to their own assigned work:

* a case assigned through an inspection or intervention, or a newly reported
  case that has not yet been assigned to anyone;
* inspections assigned to the technician;
* interventions assigned to the technician;
* follow-ups belonging to the technician's interventions;
* farmers and farms connected to the technician's authorized cases.

The rules are expressed as SQL clauses so every list, search, report, dashboard
query, and farm-map projection applies the same scope in the database. Routes
must not rely on the frontend to hide records.
"""

from flask import g
from sqlalchemy import and_, false, or_, select

from app.extensions import db
from app.models import (
    Farm,
    Farmer,
    FollowUp,
    Inspection,
    Intervention,
    PestCase,
    UserRole,
)


def current_user():
    return getattr(g, "current_user", None)


def _resolve_user(user):
    return user if user is not None else current_user()


def is_admin(user) -> bool:
    return user is not None and user.role == UserRole.ADMIN.value


def is_technician(user) -> bool:
    return user is not None and user.role == UserRole.TECHNICIAN.value


def _scope_for(user, clause_factory):
    user = _resolve_user(user)
    if user is None or is_admin(user):
        return None
    if not is_technician(user):
        return false()
    return clause_factory(user)


def case_visibility_clause(user=None):
    def build(technician):
        user_id = technician.id
        assigned = or_(
            select(Inspection.id)
            .where(
                Inspection.pest_case_id == PestCase.id,
                Inspection.assigned_to_user_id == user_id,
            )
            .correlate(PestCase)
            .exists(),
            select(Intervention.id)
            .where(
                Intervention.pest_case_id == PestCase.id,
                Intervention.assigned_to_user_id == user_id,
            )
            .correlate(PestCase)
            .exists(),
        )
        # A technician may still see a case they just reported while it has no
        # workflow assignment. Once any inspection or intervention is assigned,
        # the explicit assignee rule takes over and the reporter no longer sees
        # records that belong to another technician.
        unassigned_reported = and_(
            PestCase.reported_by_user_id == user_id,
            ~select(Inspection.id)
            .where(Inspection.pest_case_id == PestCase.id)
            .correlate(PestCase)
            .exists(),
            ~select(Intervention.id)
            .where(Intervention.pest_case_id == PestCase.id)
            .correlate(PestCase)
            .exists(),
        )
        return or_(assigned, unassigned_reported)

    return _scope_for(user, build)


def inspection_visibility_clause(user=None):
    def build(technician):
        return Inspection.assigned_to_user_id == technician.id

    return _scope_for(user, build)


def intervention_visibility_clause(user=None):
    def build(technician):
        return Intervention.assigned_to_user_id == technician.id

    return _scope_for(user, build)


def follow_up_visibility_clause(user=None):
    def build(technician):
        return FollowUp.intervention_id.in_(
            select(Intervention.id)
            .where(Intervention.assigned_to_user_id == technician.id)
            .correlate(None)
        )

    return _scope_for(user, build)


def farm_visibility_clause(user=None):
    def build(technician):
        case_clause = case_visibility_clause(technician)
        return Farm.id.in_(select(PestCase.farm_id).where(case_clause))

    return _scope_for(user, build)


def farmer_visibility_clause(user=None):
    def build(technician):
        case_clause = case_visibility_clause(technician)
        farm_ids = select(PestCase.farm_id).where(case_clause)
        return Farmer.id.in_(select(Farm.farmer_id).where(Farm.id.in_(farm_ids)))

    return _scope_for(user, build)


def apply_case_scope(statement, user=None):
    clause = case_visibility_clause(user)
    return statement if clause is None else statement.where(clause)


def apply_inspection_scope(statement, user=None):
    clause = inspection_visibility_clause(user)
    return statement if clause is None else statement.where(clause)


def apply_intervention_scope(statement, user=None):
    clause = intervention_visibility_clause(user)
    return statement if clause is None else statement.where(clause)


def apply_follow_up_scope(statement, user=None):
    clause = follow_up_visibility_clause(user)
    return statement if clause is None else statement.where(clause)


def apply_farm_scope(statement, user=None):
    clause = farm_visibility_clause(user)
    return statement if clause is None else statement.where(clause)


def apply_farmer_scope(statement, user=None):
    clause = farmer_visibility_clause(user)
    return statement if clause is None else statement.where(clause)


def can_view_case(user, case) -> bool:
    if case is None:
        return False
    user = _resolve_user(user)
    if user is None or is_admin(user):
        return True
    clause = case_visibility_clause(user)
    if clause is None:
        return True
    return (
        db.session.scalar(
            select(PestCase.id).where(PestCase.id == case.id, clause)
        )
        is not None
    )


def can_view_farmer(user, farmer) -> bool:
    if farmer is None:
        return False
    user = _resolve_user(user)
    if user is None or is_admin(user):
        return True
    clause = farmer_visibility_clause(user)
    if clause is None:
        return True
    return (
        db.session.scalar(
            select(Farmer.id).where(Farmer.id == farmer.id, clause)
        )
        is not None
    )


def can_view_farm(user, farm) -> bool:
    if farm is None:
        return False
    user = _resolve_user(user)
    if user is None or is_admin(user):
        return True
    clause = farm_visibility_clause(user)
    if clause is None:
        return True
    return (
        db.session.scalar(select(Farm.id).where(Farm.id == farm.id, clause))
        is not None
    )


def can_view_inspection(user, inspection) -> bool:
    if inspection is None:
        return False
    user = _resolve_user(user)
    if user is None or is_admin(user):
        return True
    return is_technician(user) and inspection.assigned_to_user_id == user.id


def can_view_intervention(user, intervention) -> bool:
    if intervention is None:
        return False
    user = _resolve_user(user)
    if user is None or is_admin(user):
        return True
    return is_technician(user) and intervention.assigned_to_user_id == user.id


def can_view_follow_up(user, follow_up) -> bool:
    if follow_up is None:
        return False
    intervention = follow_up.intervention
    if intervention is None:
        intervention = db.session.get(Intervention, follow_up.intervention_id)
    return can_view_intervention(user, intervention)
