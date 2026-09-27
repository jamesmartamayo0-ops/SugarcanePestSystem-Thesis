from unittest.mock import Mock, patch

from app import create_app
from app.extensions import db


def test_health_reports_database_connected(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-placeholder")
    app = create_app()

    with patch.object(db.session, "execute", return_value=Mock(scalar_one=Mock(return_value=1))) as execute:
        response = app.test_client().get("/api/v1/health")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {
        "data": {
            "service": "sugarcane-pest-api",
            "backend": "connected",
            "database": "connected",
        },
        "message": "System health check successful.",
    }
    assert str(execute.call_args.args[0]) == "SELECT 1"


def test_health_hides_database_failure(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-placeholder")
    app = create_app()

    with patch.object(db.session, "execute", side_effect=RuntimeError("sensitive database detail")):
        response = app.test_client().get("/api/v1/health")

    assert response.status_code == 503
    assert response.is_json
    assert response.get_json() == {
        "data": {
            "service": "sugarcane-pest-api",
            "backend": "connected",
            "database": "unavailable",
        },
        "message": "Database health check failed.",
    }
    assert "sensitive database detail" not in response.get_data(as_text=True)


def test_health_without_password_skips_database(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "")
    app = create_app()

    with patch.object(db.session, "execute") as execute:
        response = app.test_client().get("/api/v1/health")

    assert response.status_code == 503
    assert response.get_json()["data"]["database"] == "unavailable"
    execute.assert_not_called()
