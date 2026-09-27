from flask import Flask
from flask_cors import CORS

from app.config import configure_app
from app.extensions import db, migrate
from app.routes.health import health_bp


def create_app() -> Flask:
    app = Flask(__name__)
    configure_app(app)

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(
        app,
        resources={r"^/api/.*$": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
    )

    app.register_blueprint(health_bp)
    return app
