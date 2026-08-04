from app import db
from app.models import Notification, Transaction, User, SiteSetting
from datetime import datetime
from functools import wraps
from flask import abort
from flask_login import current_user


def notify_user(user_id, message, link=None):
    """Create an in-app notification for a user."""
    note = Notification(user_id=user_id, message=message, link=link)
    db.session.add(note)
    db.session.commit()


def notify_all_admins(message, link=None):
    """Send a notification to all admin users."""
    admins = User.query.filter(
        (User.is_admin == True) | (User.is_super_admin == True)
    ).all()
    for admin in admins:
        note = Notification(user_id=admin.id, message=message, link=link)
        db.session.add(note)
    db.session.commit()


def credit_user(user_id, amount, description, txn_type="commission"):
    """Credit a user's balance and record a transaction."""
    user = User.query.get(user_id)
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


def check_referral_milestones(user):
    """
    Referral reward structure:
    - 3 referrals: one-time ₦2,000 bonus (milestone_3_paid flag)
    - Referrals 4–20: ₦500 credited for each individual referral in that range
    """
    milestone_3_bonus = float(SiteSetting.get("milestone_3_bonus", "2000"))
    per_referral_bonus = float(SiteSetting.get("per_referral_bonus", "500"))

    # One-time ₦2,000 bonus when the user first reaches 3 referrals
    if user.referral_count >= 3 and not user.milestone_3_paid:
        user.milestone_3_paid = True
        db.session.commit()
        credit_user(user.id, milestone_3_bonus, "🎉 Milestone reward: 3 successful referrals!")
        notify_user(
            user.id,
            f"Congratulations! You've reached 3 referrals. ₦{milestone_3_bonus:,.0f} has been credited to your account!",
            "/dashboard/transactions",
        )

    # ₦500 for each referral from the 4th up to and including the 20th.
    # We check the exact current referral_count so each new referral in that
    # range triggers exactly one credit (called once per new referral approval).
    if 4 <= user.referral_count <= 20:
        credit_user(
            user.id,
            per_referral_bonus,
            f"💰 Referral bonus: referral #{user.referral_count} reward!",
        )
        notify_user(
            user.id,
            f"You earned ₦{per_referral_bonus:,.0f} for referral #{user.referral_count}!",
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
