from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.extensions import db


health_bp = Blueprint("health", __name__)


@health_bp.get("/api/v1/health")
def health():
    data = {
        "service": "sugarcane-pest-api",
        "backend": "connected",
    }

    if current_app.config["DB_PASSWORD_CONFIGURED"]:
        try:
            db.session.execute(text("SELECT 1")).scalar_one()
        except Exception:
            current_app.logger.exception("Database health check failed")
            pass
        else:
            data["database"] = "connected"
            return jsonify({"data": data, "message": "System health check successful."})

    data["database"] = "unavailable"
    return jsonify({"data": data, "message": "Database health check failed."}), 503
