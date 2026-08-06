from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
import os

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
socketio = SocketIO()


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    secret = os.environ.get("SECRET_KEY")
    if not secret:
        import warnings
        warnings.warn("SECRET_KEY env var not set — using insecure default. Set it in production!", stacklevel=2)
        secret = "bestpay-secret-key-change-in-production"
    app.config["SECRET_KEY"] = secret

    # ── Primary database: PostgreSQL ──────────────────────────────────────────
    pg_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://bestpaydatabase_user:EPDoIdqRoc4zNEPI8d3EylImdDCAu1PN@dpg-d9q6j86417fc73fllglg-a.oregon-postgres.render.com/bestpaydatabase"
    )
    # Render sometimes returns postgres:// — SQLAlchemy needs postgresql://
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = pg_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["WTF_CSRF_ENABLED"] = True

    # ── Cloudinary config (plug in your credentials via env vars) ─────────────
    app.config["CLOUDINARY_CLOUD_NAME"] = os.environ.get("CLOUDINARY_CLOUD_NAME", "e3yf5gll")
    app.config["CLOUDINARY_API_KEY"] = os.environ.get("CLOUDINARY_API_KEY", "476515679863575")
    app.config["CLOUDINARY_API_SECRET"] = os.environ.get("CLOUDINARY_API_SECRET", "JmPcndoNLIRj7NWSft1Q5lT2dCk")

    import cloudinary
    cloudinary.config(
        cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=app.config["CLOUDINARY_API_KEY"],
        api_secret=app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="gevent")

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.admin import admin_bp
    from app.routes.super_admin import super_admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(super_admin_bp)

    # Register SocketIO event handlers
    from app.routes import socket_events  # noqa: F401

    with app.app_context():
        db.create_all()

    return app
