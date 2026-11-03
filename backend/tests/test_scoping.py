"""Focused authorization rules for assigned operational work."""

from types import SimpleNamespace

from flask import Flask

from app.models import UserRole
from app.scoping import can_act_on_assigned_work


def _user(role: str, user_id: int = 1):
    return SimpleNamespace(id=user_id, role=role)


def _record(assigned_to_user_id: int):
    return SimpleNamespace(assigned_to_user_id=assigned_to_user_id)


def test_admin_can_act_on_work_assigned_to_a_technician():
    admin = _user(UserRole.ADMIN.value, user_id=1)

    assert can_act_on_assigned_work(admin, _record(assigned_to_user_id=2)) is True


def test_technician_can_act_only_on_own_assigned_work():
    technician = _user(UserRole.TECHNICIAN.value, user_id=2)

    assert can_act_on_assigned_work(technician, _record(assigned_to_user_id=2)) is True
    assert can_act_on_assigned_work(technician, _record(assigned_to_user_id=3)) is False


def test_unknown_or_missing_actor_is_denied():
    with Flask(__name__).app_context():
        assert can_act_on_assigned_work(None, _record(assigned_to_user_id=2)) is False

    no_assignment = SimpleNamespace()
    assert (
        can_act_on_assigned_work(
            _user(UserRole.ADMIN.value),
            no_assignment,
        )
        is True
    )
    assert (
        can_act_on_assigned_work(
            _user(UserRole.TECHNICIAN.value),
            no_assignment,
        )
        is False
    )
