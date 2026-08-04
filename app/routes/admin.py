from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Transaction, Withdrawal, SupportTicket, TicketReply, Notification, SiteSetting
from app.forms import TicketReplyForm, AdminUserEditForm
from app.helpers import admin_required, notify_user, check_referral_milestones
from datetime import datetime

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
    user = User.query.get_or_404(user_id)
    form = AdminUserEditForm(obj=user)
    if form.validate_on_submit():
        user.display_name = form.display_name.data
        user.email = form.email.data
        user.balance = form.balance.data
        user.is_approved = form.is_approved.data
        user.registration_fee_paid = form.registration_fee_paid.data
        if not current_user.is_super_admin:
            # Regular admins can't promote to admin
            pass
        else:
            user.is_admin = form.is_admin.data
        db.session.commit()
        flash(f"User {user.email} updated.", "success")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    txns = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.created_at.desc()).limit(10).all()
    referrals = User.query.filter_by(referred_by=user.referral_code).all()
    return render_template("admin/user_detail.html", user=user, form=form, txns=txns, referrals=referrals)


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
    user = User.query.get_or_404(user_id)
    user.registration_fee_paid = True
    user.is_approved = True

    # Record the deposit transaction
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
            referrer.referral_count += 1
            db.session.commit()
            check_referral_milestones(referrer)
            notify_user(
                referrer.id,
                f"🎉 {user.display_name} just joined using your referral link! Your referral count is now {referrer.referral_count}.",
                "/dashboard/referrals"
            )

    db.session.commit()
    notify_user(
        user_id,
        "✅ Your payment has been verified! Your account is now active. Start referring friends to earn rewards!",
        "/dashboard"
    )
    flash(f"{user.display_name}'s account has been approved.", "success")
    return redirect(url_for("admin.payments"))


@admin_bp.route("/payments/<int:user_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_payment(user_id):
    user = User.query.get_or_404(user_id)
    user.payment_submitted = False
    db.session.commit()
    notify_user(
        user_id,
        "❌ Your payment could not be verified. Please re-submit your payment confirmation.",
        "/dashboard/activate"
    )
    flash(f"{user.display_name}'s payment has been rejected.", "warning")
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
    w = Withdrawal.query.get_or_404(wid)
    if w.status != "pending":
        flash("This withdrawal has already been processed.", "warning")
        return redirect(url_for("admin.withdrawals"))

    w.status = "approved"
    w.approved_at = datetime.utcnow()
    w.approved_by = current_user.id

    # Update the matching transaction
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
    flash(f"Withdrawal of ₦{w.amount:,.0f} approved.", "success")
    return redirect(url_for("admin.withdrawals"))


@admin_bp.route("/withdrawals/<int:wid>/reject", methods=["POST"])
@login_required
@admin_required
def reject_withdrawal(wid):
    w = Withdrawal.query.get_or_404(wid)
    reason = request.form.get("reason", "No reason provided.")
    if w.status != "pending":
        flash("Already processed.", "warning")
        return redirect(url_for("admin.withdrawals"))

    # Refund the user's balance with the full amount they were charged
    # (the transaction stores the pre-tax amount; w.amount is post-tax)
    user = User.query.get(w.user_id)
    txn = Transaction.query.filter_by(
        user_id=w.user_id, type="withdrawal", status="pending"
    ).order_by(Transaction.created_at.desc()).first()
    refund_amount = txn.amount if txn else w.amount
    if user:
        user.balance += refund_amount

    w.status = "rejected"
    w.rejection_reason = reason
    w.approved_by = current_user.id

    if txn:
        txn.status = "rejected"

    db.session.commit()
    notify_user(
        w.user_id,
        f"❌ Your withdrawal of ₦{refund_amount:,.0f} was rejected. Reason: {reason}. Your balance has been refunded.",
        "/dashboard/withdraw"
    )
    flash(f"Withdrawal rejected and ₦{refund_amount:,.0f} refunded to user.", "warning")
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
