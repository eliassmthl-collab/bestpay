from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import User, Transaction, Withdrawal, SupportTicket, TicketReply, Notification, SiteSetting
from app.forms import (
    WithdrawalForm, SupportTicketForm, TicketReplyForm, ProfileForm,
    ChangePasswordForm, SetWithdrawalPasswordForm, ResetWithdrawalPasswordForm,
    PaymentProofForm, WITHDRAWAL_AMOUNTS
)
from app.helpers import notify_user, notify_all_admins, activated_required, push_update
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/")
@login_required
def index():
    if current_user.is_admin or current_user.is_super_admin:
        return redirect(url_for("admin.index"))

    if not current_user.registration_fee_paid or not current_user.is_approved:
        return redirect(url_for("dashboard.activate"))

    referral_link = request.host_url.rstrip("/") + "/signup?ref=" + current_user.referral_code
    recent_txns = Transaction.query.filter_by(user_id=current_user.id).order_by(
        Transaction.created_at.desc()
    ).limit(5).all()

    referred_users = User.query.filter_by(referred_by=current_user.referral_code).all()
    approved_referrals = [u for u in referred_users if u.is_approved]

    return render_template(
        "dashboard/index.html",
        referral_link=referral_link,
        recent_txns=recent_txns,
        referred_users=referred_users,
        approved_referrals=approved_referrals,
    )


@dashboard_bp.route("/activate", methods=["GET", "POST"])
@login_required
def activate():
    if current_user.registration_fee_paid and current_user.is_approved:
        return redirect(url_for("dashboard.index"))

    bank_name = SiteSetting.get("bank_name", "GTBank")
    account_number = SiteSetting.get("account_number", "0123456789")
    account_name = SiteSetting.get("account_name", "BestPay Enterprises")
    reg_fee = SiteSetting.get("registration_fee", "1000")

    form = PaymentProofForm()

    if form.validate_on_submit() and not current_user.payment_submitted:
        # Upload receipt to Cloudinary
        proof_url = None
        if form.receipt.data:
            try:
                import cloudinary.uploader
                result = cloudinary.uploader.upload(
                    form.receipt.data,
                    folder="bestpay/receipts",
                    resource_type="auto",
                )
                proof_url = result.get("secure_url")
            except Exception as e:
                flash(f"Receipt upload failed: {str(e)}. Please try again.", "danger")
                return render_template(
                    "dashboard/activate.html",
                    bank_name=bank_name,
                    account_number=account_number,
                    account_name=account_name,
                    reg_fee=reg_fee,
                    form=form,
                )

        current_user.payment_submitted = True
        current_user.payment_proof_url = proof_url
        db.session.commit()

        notify_all_admins(
            f"💰 New payment submitted by {current_user.display_name} ({current_user.email}). Please verify and approve.",
            "/admin/payments"
        )
        flash("Payment confirmation submitted! Your account will be activated once verified by an admin.", "success")
        return redirect(url_for("dashboard.activate"))

    return render_template(
        "dashboard/activate.html",
        bank_name=bank_name,
        account_number=account_number,
        account_name=account_name,
        reg_fee=reg_fee,
        form=form,
    )


@dashboard_bp.route("/referrals")
@login_required
@activated_required
def referrals():
    referral_link = request.host_url.rstrip("/") + "/signup?ref=" + current_user.referral_code
    referred_users = User.query.filter_by(referred_by=current_user.referral_code).order_by(
        User.created_at.desc()
    ).all()
    return render_template("dashboard/referrals.html", referred_users=referred_users, referral_link=referral_link)


@dashboard_bp.route("/withdraw", methods=["GET", "POST"])
@login_required
@activated_required
def withdraw():
    # Must have withdrawal password set
    if not current_user.withdrawal_password:
        flash("You must set a withdrawal password before you can make a withdrawal.", "warning")
        return redirect(url_for("dashboard.profile"))

    # Must have at least 3 active referrals
    if current_user.referral_count < 3:
        flash(
            f"You need at least 3 active referrals to withdraw. "
            f"You currently have {current_user.referral_count}.",
            "warning"
        )
        return redirect(url_for("dashboard.index"))

    form = WithdrawalForm()
    # Filter choices to only amounts the user can afford
    affordable = [(str(a), f"₦{a:,}") for a in WITHDRAWAL_AMOUNTS if a <= current_user.balance]
    form.amount.choices = affordable if affordable else [("0", "Insufficient balance")]

    if form.validate_on_submit():
        requested_amount = float(form.amount.data)

        # Validate withdrawal password
        if not check_password_hash(current_user.withdrawal_password, form.withdrawal_password.data):
            flash("Incorrect withdrawal password.", "danger")
            history = Withdrawal.query.filter_by(user_id=current_user.id).order_by(
                Withdrawal.created_at.desc()
            ).all()
            return render_template("dashboard/withdraw.html", form=form, history=history)

        if requested_amount > current_user.balance:
            flash("Insufficient balance.", "danger")
        elif requested_amount <= 0:
            flash("Please select a valid amount.", "danger")
        else:
            # Silent 10% tax
            tax_rate = float(SiteSetting.get("withdrawal_tax_rate", "0.10"))
            actual_amount = round(requested_amount * (1 - tax_rate), 2)

            try:
                # Create transaction first, then link withdrawal to it
                txn = Transaction(
                    user_id=current_user.id,
                    type="withdrawal",
                    amount=requested_amount,
                    status="pending",
                    description=f"Withdrawal to {form.bank_name.data} - {form.account_number.data}",
                )
                db.session.add(txn)
                db.session.flush()  # get txn.id before commit

                withdrawal = Withdrawal(
                    user_id=current_user.id,
                    transaction_id=txn.id,  # FK link
                    amount=actual_amount,
                    bank_name=form.bank_name.data,
                    account_number=form.account_number.data,
                    account_name=form.account_name.data,
                )
                current_user.balance -= requested_amount
                db.session.add(withdrawal)
                db.session.commit()

                notify_all_admins(
                    f"💸 Withdrawal request of ₦{requested_amount:,.0f} from {current_user.display_name}.",
                    "/admin/withdrawals"
                )
                flash("Withdrawal request submitted! You'll be notified once processed.", "success")
                return redirect(url_for("dashboard.withdraw"))
            except Exception:
                db.session.rollback()
                flash("Something went wrong. Please try again.", "danger")

    history = Withdrawal.query.filter_by(user_id=current_user.id).order_by(
        Withdrawal.created_at.desc()
    ).all()
    return render_template("dashboard/withdraw.html", form=form, history=history)


@dashboard_bp.route("/transactions")
@login_required
@activated_required
def transactions():
    page = request.args.get("page", 1, type=int)
    txns = Transaction.query.filter_by(user_id=current_user.id).order_by(
        Transaction.created_at.desc()
    ).paginate(page=page, per_page=15)
    return render_template("dashboard/transactions.html", txns=txns)


@dashboard_bp.route("/support", methods=["GET", "POST"])
@login_required
def support():
    form = SupportTicketForm()
    if form.validate_on_submit():
        ticket = SupportTicket(
            user_id=current_user.id,
            subject=form.subject.data,
            message=form.message.data,
        )
        db.session.add(ticket)
        db.session.commit()
        notify_all_admins(
            f"🎫 New support ticket from {current_user.display_name}: \"{form.subject.data}\"",
            f"/admin/tickets/{ticket.id}"
        )
        flash("Support ticket submitted! We'll get back to you soon.", "success")
        return redirect(url_for("dashboard.support"))

    tickets = SupportTicket.query.filter_by(user_id=current_user.id).order_by(
        SupportTicket.created_at.desc()
    ).all()
    return render_template("dashboard/support.html", form=form, tickets=tickets)


@dashboard_bp.route("/support/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def ticket_detail(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if ticket.user_id != current_user.id:
        flash("Access denied.", "danger")
        return redirect(url_for("dashboard.support"))

    form = TicketReplyForm()
    if form.validate_on_submit():
        if ticket.status == "closed":
            flash("This ticket is closed.", "warning")
        else:
            reply = TicketReply(
                ticket_id=ticket_id,
                user_id=current_user.id,
                message=form.message.data,
            )
            db.session.add(reply)
            db.session.commit()
            flash("Reply sent.", "success")
            return redirect(url_for("dashboard.ticket_detail", ticket_id=ticket_id))

    return render_template("dashboard/ticket_detail.html", ticket=ticket, form=form)


@dashboard_bp.route("/support/<int:ticket_id>/close", methods=["POST"])
@login_required
def close_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if ticket.user_id != current_user.id:
        flash("Access denied.", "danger")
    else:
        ticket.status = "closed"
        db.session.commit()
        flash("Ticket closed.", "info")
    return redirect(url_for("dashboard.ticket_detail", ticket_id=ticket_id))


@dashboard_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    pw_form = ChangePasswordForm()
    set_wp_form = SetWithdrawalPasswordForm()

    if form.validate_on_submit():
        current_user.display_name = form.display_name.data
        current_user.phone = form.phone.data
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("dashboard.profile"))

    return render_template(
        "dashboard/profile.html",
        form=form,
        pw_form=pw_form,
        set_wp_form=set_wp_form,
    )


@dashboard_bp.route("/profile/change-password", methods=["POST"])
@login_required
def change_password():
    pw_form = ChangePasswordForm()
    if pw_form.validate_on_submit():
        if not check_password_hash(current_user.password, pw_form.current_password.data):
            flash("Current password is incorrect.", "danger")
        else:
            current_user.password = generate_password_hash(pw_form.new_password.data)
            db.session.commit()
            flash("Password changed successfully.", "success")
    else:
        for field, errors in pw_form.errors.items():
            for error in errors:
                flash(error, "danger")
    return redirect(url_for("dashboard.profile"))


@dashboard_bp.route("/profile/set-withdrawal-password", methods=["POST"])
@login_required
def set_withdrawal_password():
    form = SetWithdrawalPasswordForm()
    if form.validate_on_submit():
        current_user.withdrawal_password = generate_password_hash(form.withdrawal_password.data)
        db.session.commit()
        flash("Withdrawal password set successfully.", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(error, "danger")
    return redirect(url_for("dashboard.profile"))


@dashboard_bp.route("/withdrawal-password/reset/<token>", methods=["GET", "POST"])
def reset_withdrawal_password(token):
    """Public route — user opens this link sent by admin."""
    user = User.query.filter_by(withdrawal_reset_token=token).first_or_404()

    if user.withdrawal_reset_expires and user.withdrawal_reset_expires < datetime.utcnow():
        flash("This reset link has expired. Please contact support for a new one.", "danger")
        return redirect(url_for("auth.login"))

    form = ResetWithdrawalPasswordForm()
    if form.validate_on_submit():
        user.withdrawal_password = generate_password_hash(form.withdrawal_password.data)
        user.withdrawal_reset_token = None
        user.withdrawal_reset_expires = None
        db.session.commit()
        flash("Withdrawal password reset successfully. You can now log in and withdraw.", "success")
        return redirect(url_for("auth.login"))

    return render_template("dashboard/reset_withdrawal_password.html", form=form, token=token)


@dashboard_bp.route("/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"status": "ok"})


@dashboard_bp.route("/notifications")
@login_required
def notifications():
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    for n in notes:
        n.is_read = True
    db.session.commit()
    return render_template("dashboard/notifications.html", notifications=notes)
