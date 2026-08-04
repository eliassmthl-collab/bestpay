from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField,
    FloatField, TextAreaField, SelectField, HiddenField
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, Optional,
    NumberRange, ValidationError
)


class SignupForm(FlaskForm):
    display_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("Email Address", validators=[DataRequired(), Email()])
    phone = StringField("Phone Number", validators=[DataRequired(), Length(min=10, max=20)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])
    referral_code = StringField("Referral Code (Optional)", validators=[Optional(), Length(max=20)])
    submit = SubmitField("Create Account")


class LoginForm(FlaskForm):
    email = StringField("Email Address", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Log In")


WITHDRAWAL_AMOUNTS = [2000, 5000, 10000, 30000, 80000, 200000, 500000, 1000000]

class WithdrawalForm(FlaskForm):
    amount = SelectField(
        "Amount (₦)",
        choices=[(str(a), f"₦{a:,}") for a in WITHDRAWAL_AMOUNTS],
        validators=[DataRequired()],
    )
    bank_name = StringField("Bank Name", validators=[DataRequired(), Length(max=100)])
    account_number = StringField("Account Number", validators=[DataRequired(), Length(min=10, max=20)])
    account_name = StringField("Account Name", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Submit Withdrawal Request")


class SupportTicketForm(FlaskForm):
    subject = StringField("Subject", validators=[DataRequired(), Length(max=200)])
    message = TextAreaField("Message", validators=[DataRequired(), Length(min=10)])
    submit = SubmitField("Submit Ticket")


class TicketReplyForm(FlaskForm):
    message = TextAreaField("Reply", validators=[DataRequired(), Length(min=2)])
    submit = SubmitField("Send Reply")


class ProfileForm(FlaskForm):
    display_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField("Phone Number", validators=[Optional(), Length(max=20)])
    submit = SubmitField("Update Profile")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Change Password")


class SiteSettingsForm(FlaskForm):
    bank_name = StringField("Bank Name", validators=[DataRequired()])
    account_number = StringField("Account Number", validators=[DataRequired()])
    account_name = StringField("Account Name", validators=[DataRequired()])
    platform_name = StringField("Platform Name", validators=[DataRequired()])
    registration_fee = StringField("Registration Fee (₦)", validators=[DataRequired()])
    milestone_3_bonus = StringField("3-Referral Milestone Bonus (₦)", validators=[DataRequired()])
    per_referral_bonus = StringField("Per-Referral Bonus for refs 4–20 (₦)", validators=[DataRequired()])
    withdrawal_tax_rate = StringField("Withdrawal Tax Rate (e.g. 0.10 for 10%)", validators=[DataRequired()])
    submit = SubmitField("Save Settings")


class AdminUserEditForm(FlaskForm):
    display_name = StringField("Full Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    balance = FloatField("Balance (₦)", validators=[DataRequired()])
    is_admin = BooleanField("Is Admin")
    is_approved = BooleanField("Account Approved")
    registration_fee_paid = BooleanField("Registration Fee Paid")
    submit = SubmitField("Update User")
