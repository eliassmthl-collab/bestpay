from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from app import db
from app.models import User, Transaction, Withdrawal, SupportTicket, TicketReply, Notification, SiteSetting
from app.forms import TicketReplyForm, AdminUserEditForm
from app.helpers import admin_required, notify_user, check_referral_milestones, push_update, push_admin_update
from app.models import generate_token
from datetime import datetime, timedelta

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@login_required
@admin_required
def index():
    total_users = User.query.filter_by(is_admin=False, is_super_admin=False).count()
    pending_payments = User.query.filter_by(payment_submitted=True, is_approved=False).count()
    pending_withdrawals = Withdrawal.query.filter_by(status="pending").count()
    open_tickets = SupportTicket.query.filter_by(status="open").count()
    total_approved = User.query.filter_by(is_approved=True, is_admin=False, is_super_admin=False).count()

    total_deposited = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        type="deposit", status="approved"
    ).scalar() or 0

    total_withdrawn = db.session.query(db.func.sum(Withdrawal.amount)).filter_by(
        status="approved"
    ).scalar() or 0

    recent_users = User.query.filter_by(is_admin=False, is_super_admin=False).order_by(
        User.created_at.desc()
    ).limit(5).all()

    return render_template(
        "admin/index.html",
        total_users=total_users,
        pending_payments=pending_payments,
        pending_withdrawals=pending_withdrawals,
        open_tickets=open_tickets,
        total_approved=total_approved,
        total_deposited=total_deposited,
        total_withdrawn=total_withdrawn,
        recent_users=recent_users,
    )


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "")
    query = User.query.filter_by(is_super_admin=False)
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )
    users_page = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/users.html", users=users_page, search=search)


@admin_bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def user_detail(user_id):
    user = db.session.get(User, user_id) or abort(404)
    form = AdminUserEditForm(obj=user)
    if form.validate_on_submit():
        user.display_name = form.display_name.data
        user.email = form.email.data
        user.balance = form.balance.data
        user.is_approved = form.is_approved.data
        user.registration_fee_paid = form.registration_fee_paid.data
        if current_user.is_super_admin:
            user.is_admin = form.is_admin.data
        db.session.commit()
        flash(f"User {user.email} updated.", "success")
        # Push balance update to user
        push_update(user.id, "balance_update", {
            "balance": user.balance,
            "balance_fmt": "{:,.0f}".format(user.balance),
        })
        return redirect(url_for("admin.user_detail", user_id=user_id))

    txns = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.created_at.desc()).limit(10).all()
    referrals = User.query.filter_by(referred_by=user.referral_code).all()

    # Generate withdrawal reset token info
    reset_link = None
    if user.withdrawal_reset_token and user.withdrawal_reset_expires and user.withdrawal_reset_expires > datetime.utcnow():
        reset_link = url_for("dashboard.reset_withdrawal_password", token=user.withdrawal_reset_token, _external=True)

    return render_template(
        "admin/user_detail.html",
        user=user, form=form, txns=txns, referrals=referrals,
        reset_link=reset_link,
    )


@admin_bp.route("/users/<int:user_id>/generate-withdrawal-reset", methods=["POST"])
@login_required
@admin_required
def generate_withdrawal_reset(user_id):
    """Generate a one-time withdrawal password reset link (expires in 1 hour)."""
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.users"))

    token = generate_token(48)
    user.withdrawal_reset_token = token
    user.withdrawal_reset_expires = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()

    reset_link = url_for("dashboard.reset_withdrawal_password", token=token, _external=True)
    flash(
        f"Reset link generated (expires in 1 hour). Copy it and send to the user manually: {reset_link}",
        "info"
    )
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/payments")
@login_required
@admin_required
def payments():
    pending = User.query.filter_by(payment_submitted=True, is_approved=False).order_by(
        User.created_at.desc()
    ).all()
    approved = User.query.filter_by(is_approved=True, is_admin=False, is_super_admin=False).order_by(
        User.created_at.desc()
    ).limit(20).all()
    return render_template("admin/payments.html", pending=pending, approved=approved)


@admin_bp.route("/payments/<int:user_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_payment(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.payments"))

    try:
        user.registration_fee_paid = True
        user.is_approved = True

        txn = Transaction(
            user_id=user_id,
            type="deposit",
            amount=float(SiteSetting.get("registration_fee", "1000")),
            status="approved",
            description="Registration fee payment",
            approved_by=current_user.id,
        )
        db.session.add(txn)

        # Credit the referrer if applicable
        if user.referred_by:
            referrer = User.query.filter_by(referral_code=user.referred_by).first()
            if referrer and referrer.is_approved:
                # referral_count is now computed, so just trigger milestones
                db.session.flush()
                check_referral_milestones(referrer)
                notify_user(
                    referrer.id,
                    f"🎉 {user.display_name} joined using your referral link! You now have {referrer.referral_count} active referrals.",
                    "/dashboard/referrals"
                )

        db.session.commit()

        notify_user(
            user_id,
            "✅ Your payment has been verified! Your account is now active. Start referring friends to earn rewards!",
            "/dashboard"
        )

        # Push real-time update to the user
        push_update(user_id, "account_approved", {
            "is_approved": True,
            "registration_fee_paid": True,
        })

        flash(f"{user.display_name}'s account has been approved.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error approving payment: {str(e)}", "danger")

    return redirect(url_for("admin.payments"))


@admin_bp.route("/payments/<int:user_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_payment(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.payments"))

    try:
        user.payment_submitted = False
        db.session.commit()
        notify_user(
            user_id,
            "❌ Your payment could not be verified. Please re-submit your payment confirmation.",
            "/dashboard/activate"
        )
        flash(f"{user.display_name}'s payment has been rejected.", "warning")
    except Exception:
        db.session.rollback()
        flash("Error rejecting payment.", "danger")

    return redirect(url_for("admin.payments"))


@admin_bp.route("/withdrawals")
@login_required
@admin_required
def withdrawals():
    pending = Withdrawal.query.filter_by(status="pending").order_by(Withdrawal.created_at.desc()).all()
    history = Withdrawal.query.filter(Withdrawal.status != "pending").order_by(
        Withdrawal.created_at.desc()
    ).limit(30).all()
    return render_template("admin/withdrawals.html", pending=pending, history=history)


@admin_bp.route("/withdrawals/<int:wid>/approve", methods=["POST"])
@login_required
@admin_required
def approve_withdrawal(wid):
    w = db.session.get(Withdrawal, wid)
    if not w:
        flash("Withdrawal not found.", "danger")
        return redirect(url_for("admin.withdrawals"))

    if w.status != "pending":
        flash("This withdrawal has already been processed.", "warning")
        return redirect(url_for("admin.withdrawals"))

    try:
        w.status = "approved"
        w.approved_at = datetime.utcnow()
        w.approved_by = current_user.id

        # Use the FK-linked transaction directly — no fragile search
        if w.transaction_id:
            txn = db.session.get(Transaction, w.transaction_id)
            if txn:
                txn.status = "approved"
                txn.approved_by = current_user.id
        else:
            # Fallback for old records without FK
            txn = Transaction.query.filter_by(
                user_id=w.user_id, type="withdrawal", status="pending"
            ).order_by(Transaction.created_at.desc()).first()
            if txn:
                txn.status = "approved"
                txn.approved_by = current_user.id

        db.session.commit()

        notify_user(
            w.user_id,
            f"✅ Your withdrawal of ₦{w.amount:,.0f} has been approved and sent to your bank account!",
            "/dashboard/transactions"
        )
        push_update(w.user_id, "withdrawal_update", {
            "withdrawal_id": w.id,
            "status": "approved",
        })

        flash(f"Withdrawal of ₦{w.amount:,.0f} approved.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error approving withdrawal: {str(e)}", "danger")

    return redirect(url_for("admin.withdrawals"))


@admin_bp.route("/withdrawals/<int:wid>/reject", methods=["POST"])
@login_required
@admin_required
def reject_withdrawal(wid):
    w = db.session.get(Withdrawal, wid)
    if not w:
        flash("Withdrawal not found.", "danger")
        return redirect(url_for("admin.withdrawals"))

    if w.status != "pending":
        flash("Already processed.", "warning")
        return redirect(url_for("admin.withdrawals"))

    reason = request.form.get("reason", "No reason provided.")

    try:
        user = db.session.get(User, w.user_id)

        # Use FK-linked transaction for refund amount
        refund_amount = w.amount
        if w.transaction_id:
            txn = db.session.get(Transaction, w.transaction_id)
            if txn:
                refund_amount = txn.amount  # pre-tax amount
                txn.status = "rejected"
        else:
            txn = Transaction.query.filter_by(
                user_id=w.user_id, type="withdrawal", status="pending"
            ).order_by(Transaction.created_at.desc()).first()
            if txn:
                refund_amount = txn.amount
                txn.status = "rejected"

        if user:
            user.balance += refund_amount

        w.status = "rejected"
        w.rejection_reason = reason
        w.approved_by = current_user.id

        db.session.commit()

        notify_user(
            w.user_id,
            f"❌ Your withdrawal of ₦{refund_amount:,.0f} was rejected. Reason: {reason}. Your balance has been refunded.",
            "/dashboard/withdraw"
        )
        push_update(w.user_id, "withdrawal_update", {
            "withdrawal_id": w.id,
            "status": "rejected",
            "rejection_reason": reason,
            "balance": user.balance if user else None,
            "balance_fmt": "{:,.0f}".format(user.balance) if user else None,
        })

        flash(f"Withdrawal rejected and ₦{refund_amount:,.0f} refunded to user.", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Error rejecting withdrawal: {str(e)}", "danger")

    return redirect(url_for("admin.withdrawals"))


@admin_bp.route("/tickets")
@login_required
@admin_required
def tickets():
    open_tickets = SupportTicket.query.filter_by(status="open").order_by(SupportTicket.created_at.desc()).all()
    closed_tickets = SupportTicket.query.filter_by(status="closed").order_by(
        SupportTicket.created_at.desc()
    ).limit(20).all()
    return render_template("admin/tickets.html", open_tickets=open_tickets, closed_tickets=closed_tickets)


@admin_bp.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
@admin_required
def ticket_detail(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    form = TicketReplyForm()
    if form.validate_on_submit():
        reply = TicketReply(
            ticket_id=ticket_id,
            user_id=current_user.id,
            message=form.message.data,
        )
        db.session.add(reply)
        db.session.commit()
        notify_user(
            ticket.user_id,
            f"📬 Admin replied to your support ticket: \"{ticket.subject}\"",
            f"/dashboard/support/{ticket_id}"
        )
        flash("Reply sent.", "success")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))
    return render_template("admin/ticket_detail.html", ticket=ticket, form=form)


@admin_bp.route("/tickets/<int:ticket_id>/close", methods=["POST"])
@login_required
@admin_required
def close_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    ticket.status = "closed"
    db.session.commit()
    notify_user(
        ticket.user_id,
        f"🔒 Your support ticket \"{ticket.subject}\" has been closed.",
        f"/dashboard/support/{ticket_id}"
    )
    flash("Ticket closed.", "info")
    return redirect(url_for("admin.tickets"))


@admin_bp.route("/transactions")
@login_required
@admin_required
def transactions():
    page = request.args.get("page", 1, type=int)
    txns = Transaction.query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=25)
    return render_template("admin/transactions.html", txns=txns)
