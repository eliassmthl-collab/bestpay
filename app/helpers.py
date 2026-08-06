from app import db
from app.models import Notification, Transaction, User, SiteSetting
from datetime import datetime
from functools import wraps
from flask import abort
from flask_login import current_user


def push_update(user_id, event="update", data=None):
    """Push a real-time SocketIO event to a specific user's room."""
    from app import socketio
    socketio.emit(event, data or {}, room=f"user_{user_id}")


def push_admin_update(event="admin_update", data=None):
    """Push a real-time SocketIO event to the admin room."""
    from app import socketio
    socketio.emit(event, data or {}, room="admins")


def notify_user(user_id, message, link=None):
    """Create an in-app notification for a user and push it via WebSocket."""
    note = Notification(user_id=user_id, message=message, link=link)
    db.session.add(note)
    db.session.commit()
    # Push real-time notification to user
    push_update(user_id, "new_notification", {
        "id": note.id,
        "message": message,
        "link": link or "#",
        "is_read": False,
        "created_at": note.created_at.strftime("%b %d, %H:%M"),
    })


def notify_all_admins(message, link=None):
    """Send a notification to all admin users and push via WebSocket."""
    admins = User.query.filter(
        (User.is_admin == True) | (User.is_super_admin == True)
    ).all()
    for admin in admins:
        note = Notification(user_id=admin.id, message=message, link=link)
        db.session.add(note)
    db.session.commit()
    # Push to admin room
    push_admin_update("new_notification", {"message": message, "link": link or "#"})


def credit_user(user_id, amount, description, txn_type="commission"):
    """Credit a user's balance and record a transaction."""
    user = db.session.get(User, user_id)
    if not user:
        return
    user.balance += amount
    txn = Transaction(
        user_id=user_id,
        type=txn_type,
        amount=amount,
        status="approved",
        description=description,
    )
    db.session.add(txn)
    db.session.commit()
    # Push balance update to user
    push_update(user_id, "balance_update", {
        "balance": user.balance,
        "balance_fmt": "{:,.0f}".format(user.balance),
    })


def check_referral_milestones(user):
    """
    Referral reward structure:
    - 3 referrals: one-time bonus (milestone_3_paid flag)
    - Referrals 4-20: per-referral bonus credited for each
    """
    milestone_3_bonus = float(SiteSetting.get("milestone_3_bonus", "2000"))
    per_referral_bonus = float(SiteSetting.get("per_referral_bonus", "500"))
    rc = user.referral_count  # now computed from DB

    # One-time bonus when user first reaches 3 referrals
    if rc >= 3 and not user.milestone_3_paid:
        user.milestone_3_paid = True
        db.session.commit()
        credit_user(user.id, milestone_3_bonus, "Milestone reward: 3 successful referrals!")
        notify_user(
            user.id,
            f"Congratulations! You've reached 3 referrals. ₦{milestone_3_bonus:,.0f} has been credited!",
            "/dashboard/transactions",
        )

    # Per-referral bonus for refs 4-20
    if 4 <= rc <= 20:
        credit_user(
            user.id,
            per_referral_bonus,
            f"Referral bonus: referral #{rc} reward!",
        )
        notify_user(
            user.id,
            f"You earned ₦{per_referral_bonus:,.0f} for referral #{rc}!",
            "/dashboard/transactions",
        )


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not (current_user.is_admin or current_user.is_super_admin):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_super_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def activated_required(f):
    """Decorator: user must have paid registration fee and be approved."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.registration_fee_paid or not current_user.is_approved:
            from flask import flash, redirect, url_for
            flash("Please activate your account first.", "warning")
            return redirect(url_for("dashboard.activate"))
        return f(*args, **kwargs)
    return decorated
