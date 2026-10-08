from flask import Flask
from flask_cors import CORS

from app.auth import enforce_unsafe_request, load_current_user, no_store_auth_response
from app.cli import register_cli
from app.config import configure_app
from app.extensions import db, migrate
from app.models import Farm, Farmer, User  # Register model metadata before Flask-Migrate initializes.
from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.farmers import farmers_bp
from app.routes.farms import farms_bp
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

    app.before_request(load_current_user)
    app.before_request(enforce_unsafe_request)
    app.after_request(no_store_auth_response)

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(farmers_bp)
    app.register_blueprint(farms_bp)
    register_cli(app)
    return app
