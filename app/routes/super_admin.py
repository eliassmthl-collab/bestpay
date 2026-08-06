from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, send_file, jsonify
)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app import db
from app.models import User, Transaction, Withdrawal, SiteSetting, Notification, SupportTicket
from app.forms import SiteSettingsForm, AdminUserEditForm
from app.helpers import super_admin_required, notify_user
import os
import csv
import io
import zipfile
from datetime import datetime

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
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("super_admin.users"))

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
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("super_admin.users"))
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
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("super_admin.index"))
    user.is_admin = True
    db.session.commit()
    flash(f"{user.email} is now an admin.", "success")
    return redirect(url_for("super_admin.index"))


@super_admin_bp.route("/admins/<int:user_id>/remove", methods=["POST"])
@login_required
@super_admin_required
def remove_admin(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("super_admin.index"))
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

    form.bank_name.data = SiteSetting.get("bank_name", "GTBank")
    form.account_number.data = SiteSetting.get("account_number", "0123456789")
    form.account_name.data = SiteSetting.get("account_name", "BestPay Enterprises")
    form.platform_name.data = SiteSetting.get("platform_name", "BestPay")
    form.registration_fee.data = SiteSetting.get("registration_fee", "1000")
    form.milestone_3_bonus.data = SiteSetting.get("milestone_3_bonus", "2000")
    form.per_referral_bonus.data = SiteSetting.get("per_referral_bonus", "500")
    form.withdrawal_tax_rate.data = SiteSetting.get("withdrawal_tax_rate", "0.10")
    return render_template("super_admin/settings.html", form=form)


@super_admin_bp.route("/download-csv")
@login_required
@super_admin_required
def download_csv():
    """Export all PostgreSQL tables as CSVs inside a ZIP file."""
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:

        # ── Users ──────────────────────────────────────────────────────────
        users_buf = io.StringIO()
        writer = csv.writer(users_buf)
        writer.writerow([
            "id", "email", "display_name", "phone", "referral_code", "referred_by",
            "balance", "referral_count", "registration_fee_paid", "is_approved",
            "payment_submitted", "is_admin", "is_super_admin", "milestone_3_paid",
            "has_withdrawal_password", "created_at"
        ])
        for u in User.query.order_by(User.created_at).all():
            writer.writerow([
                u.id, u.email, u.display_name, u.phone, u.referral_code, u.referred_by,
                u.balance, u.referral_count, u.registration_fee_paid, u.is_approved,
                u.payment_submitted, u.is_admin, u.is_super_admin, u.milestone_3_paid,
                bool(u.withdrawal_password), u.created_at
            ])
        zf.writestr("users.csv", users_buf.getvalue())

        # ── Transactions ───────────────────────────────────────────────────
        txns_buf = io.StringIO()
        writer = csv.writer(txns_buf)
        writer.writerow(["id", "user_id", "type", "amount", "status", "description", "created_at", "approved_by"])
        for t in Transaction.query.order_by(Transaction.created_at).all():
            writer.writerow([t.id, t.user_id, t.type, t.amount, t.status, t.description, t.created_at, t.approved_by])
        zf.writestr("transactions.csv", txns_buf.getvalue())

        # ── Withdrawals ────────────────────────────────────────────────────
        wd_buf = io.StringIO()
        writer = csv.writer(wd_buf)
        writer.writerow([
            "id", "user_id", "transaction_id", "amount", "bank_name",
            "account_number", "account_name", "status", "rejection_reason",
            "created_at", "approved_at", "approved_by"
        ])
        for w in Withdrawal.query.order_by(Withdrawal.created_at).all():
            writer.writerow([
                w.id, w.user_id, w.transaction_id, w.amount, w.bank_name,
                w.account_number, w.account_name, w.status, w.rejection_reason,
                w.created_at, w.approved_at, w.approved_by
            ])
        zf.writestr("withdrawals.csv", wd_buf.getvalue())

        # ── Support Tickets ────────────────────────────────────────────────
        st_buf = io.StringIO()
        writer = csv.writer(st_buf)
        writer.writerow(["id", "user_id", "subject", "status", "created_at"])
        for t in SupportTicket.query.order_by(SupportTicket.created_at).all():
            writer.writerow([t.id, t.user_id, t.subject, t.status, t.created_at])
        zf.writestr("support_tickets.csv", st_buf.getvalue())

        # ── Site Settings ──────────────────────────────────────────────────
        ss_buf = io.StringIO()
        writer = csv.writer(ss_buf)
        writer.writerow(["key", "value"])
        for s in SiteSetting.query.all():
            writer.writerow([s.key, s.value])
        zf.writestr("site_settings.csv", ss_buf.getvalue())

    zip_buffer.seek(0)
    filename = f"bestpay_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


@super_admin_bp.route("/transactions")
@login_required
@super_admin_required
def transactions():
    page = request.args.get("page", 1, type=int)
    txns = Transaction.query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=25)
    return render_template("super_admin/transactions.html", txns=txns)
