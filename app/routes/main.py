from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.is_super_admin:
            return redirect(url_for("super_admin.index"))
        elif current_user.is_admin:
            return redirect(url_for("admin.index"))
        return redirect(url_for("dashboard.index"))
    return render_template("main/landing.html")


@main_bp.app_errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403


@main_bp.app_errorhandler(404)
def not_found(e):
    return render_template("errors/404.html"), 404


@main_bp.app_errorhandler(500)
def server_error(e):
    return render_template("errors/500.html"), 500
