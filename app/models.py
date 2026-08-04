from app import db
from flask_login import UserMixin
from datetime import datetime
import random
import string


def generate_referral_code():
    """Generate a unique 8-character alphanumeric referral code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password = db.Column(db.String(256), nullable=False)
    referral_code = db.Column(db.String(20), unique=True, nullable=False, default=generate_referral_code)
    referred_by = db.Column(db.String(20), nullable=True)
    balance = db.Column(db.Float, default=0.0)
    referral_count = db.Column(db.Integer, default=0)
    registration_fee_paid = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    payment_submitted = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    milestone_3_paid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    transactions = db.relationship("Transaction", foreign_keys="Transaction.user_id", backref="user", lazy=True)
    withdrawals = db.relationship("Withdrawal", foreign_keys="Withdrawal.user_id", backref="user", lazy=True)
    support_tickets = db.relationship("SupportTicket", foreign_keys="SupportTicket.user_id", backref="user", lazy=True)
    notifications = db.relationship("Notification", foreign_keys="Notification.user_id", backref="user", lazy=True)

    def get_referral_link(self):
        return f"/signup?ref={self.referral_code}"

    def get_unread_notification_count(self):
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()

    def __repr__(self):
        return f"<User {self.email}>"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # deposit / withdrawal / commission
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / approved / rejected
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    approver = db.relationship("User", foreign_keys=[approved_by])


class Withdrawal(db.Model):
    __tablename__ = "withdrawals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(30), nullable=False)
    account_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / approved / rejected
    rejection_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    approver = db.relationship("User", foreign_keys=[approved_by])


class SupportTicket(db.Model):
    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="open")  # open / closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    replies = db.relationship("TicketReply", backref="ticket", lazy=True, cascade="all, delete-orphan")


class TicketReply(db.Model):
    __tablename__ = "ticket_replies"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_tickets.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User", foreign_keys=[user_id])


class SiteSetting(db.Model):
    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

    @staticmethod
    def get(key, default=None):
        setting = SiteSetting.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        setting = SiteSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = SiteSetting(key=key, value=value)
            db.session.add(setting)
        db.session.commit()


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(200), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
