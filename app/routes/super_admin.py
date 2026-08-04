from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, send_file, jsonify
)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, Transaction, Withdrawal, SiteSetting, Notification
from app.forms import SiteSettingsForm, AdminUserEditForm
from app.helpers import super_admin_required, notify_user
import os

super_admin_bp = Blueprint("super_admin", __name__, url_prefix="/super")


@super_admin_bp.route("/")
@login_required
@super_admin_required
def index():
    total_users = User.query.count()
    total_deposited = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        type="deposit", status="approved"
    ).scalar() or 0
    total_commissions = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        type="commission", status="approved"
    ).scalar() or 0
    total_withdrawn = db.session.query(db.func.sum(Withdrawal.amount)).filter_by(status="approved").scalar() or 0
    admins = User.query.filter(
        (User.is_admin == True) | (User.is_super_admin == True)
    ).all()

    return render_template(
        "super_admin/index.html",
        total_users=total_users,
        total_deposited=total_deposited,
        total_commissions=total_commissions,
        total_withdrawn=total_withdrawn,
        admins=admins,
    )


@super_admin_bp.route("/users")
@login_required
@super_admin_required
def users():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "")
    query = User.query
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )
    users_page = query.order_by(User.created_at.desc()).paginate(page=page, per_page=25)
    return render_template("super_admin/users.html", users=users_page, search=search)


@super_admin_bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@login_required
@super_admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    form = AdminUserEditForm(obj=user)
    if form.validate_on_submit():
        user.display_name = form.display_name.data
        user.email = form.email.data.lower()
        user.balance = form.balance.data
        user.is_admin = form.is_admin.data
        user.is_approved = form.is_approved.data
        user.registration_fee_paid = form.registration_fee_paid.data
        db.session.commit()
        flash(f"User {user.email} updated.", "success")
        return redirect(url_for("super_admin.user_detail", user_id=user_id))

    txns = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.created_at.desc()).all()
    referrals = User.query.filter_by(referred_by=user.referral_code).all()
    return render_template(
        "super_admin/user_detail.html",
        user=user, form=form, txns=txns, referrals=referrals
    )


@super_admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@super_admin_required
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_pw = request.form.get("new_password", "")
    if len(new_pw) < 6:
        flash("Password must be at least 6 characters.", "danger")
    else:
        user.password = generate_password_hash(new_pw)
        db.session.commit()
        flash(f"Password for {user.email} reset successfully.", "success")
    return redirect(url_for("super_admin.user_detail", user_id=user_id))


@super_admin_bp.route("/admins/add", methods=["POST"])
@login_required
@super_admin_required
def add_admin():
    user_id = request.form.get("user_id", type=int)
    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    flash(f"{user.email} is now an admin.", "success")
    return redirect(url_for("super_admin.index"))


@super_admin_bp.route("/admins/<int:user_id>/remove", methods=["POST"])
@login_required
@super_admin_required
def remove_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_super_admin:
        flash("Cannot remove super admin privileges.", "danger")
    else:
        user.is_admin = False
        db.session.commit()
        flash(f"{user.email} is no longer an admin.", "info")
    return redirect(url_for("super_admin.index"))


@super_admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@super_admin_required
def settings():
    form = SiteSettingsForm()
    if form.validate_on_submit():
        SiteSetting.set("bank_name", form.bank_name.data)
        SiteSetting.set("account_number", form.account_number.data)
        SiteSetting.set("account_name", form.account_name.data)
        SiteSetting.set("platform_name", form.platform_name.data)
        SiteSetting.set("registration_fee", form.registration_fee.data)
        SiteSetting.set("milestone_3_bonus", form.milestone_3_bonus.data)
        SiteSetting.set("per_referral_bonus", form.per_referral_bonus.data)
        SiteSetting.set("withdrawal_tax_rate", form.withdrawal_tax_rate.data)
        flash("Settings saved.", "success")
        return redirect(url_for("super_admin.settings"))

    # Pre-fill
    form.bank_name.data = SiteSetting.get("bank_name", "GTBank")
    form.account_number.data = SiteSetting.get("account_number", "0123456789")
    form.account_name.data = SiteSetting.get("account_name", "BestPay Enterprises")
    form.platform_name.data = SiteSetting.get("platform_name", "BestPay")
    form.registration_fee.data = SiteSetting.get("registration_fee", "1000")
    form.milestone_3_bonus.data = SiteSetting.get("milestone_3_bonus", "2000")
    form.per_referral_bonus.data = SiteSetting.get("per_referral_bonus", "500")
    form.withdrawal_tax_rate.data = SiteSetting.get("withdrawal_tax_rate", "0.10")
    return render_template("super_admin/settings.html", form=form)


@super_admin_bp.route("/download-db")
@login_required
@super_admin_required
def download_db():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "database.db")
    if not os.path.exists(db_path):
        flash("Database file not found.", "danger")
        return redirect(url_for("super_admin.index"))
    return send_file(db_path, as_attachment=True, download_name="bestpay_database.db")


@super_admin_bp.route("/transactions")
@login_required
@super_admin_required
def transactions():
    page = request.args.get("page", 1, type=int)
    txns = Transaction.query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=25)
    return render_template("super_admin/transactions.html", txns=txns)
