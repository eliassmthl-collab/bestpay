from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User, Transaction, SiteSetting
from app.forms import SignupForm, LoginForm
from app.helpers import notify_all_admins
from app.models import generate_referral_code

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    ref_code = request.args.get("ref", "")
    form = SignupForm()

    if form.validate_on_submit():
        # Check if email already exists
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash("An account with that email already exists.", "danger")
            return render_template("auth/signup.html", form=form, ref_code=ref_code)

        # Validate referral code if provided
        referrer = None
        if form.referral_code.data:
            referrer = User.query.filter_by(referral_code=form.referral_code.data.upper()).first()
            if not referrer:
                flash("Invalid referral code. Please check and try again.", "danger")
                return render_template("auth/signup.html", form=form, ref_code=ref_code)

        # Generate unique referral code
        code = generate_referral_code()
        while User.query.filter_by(referral_code=code).first():
            code = generate_referral_code()

        user = User(
            email=form.email.data.lower(),
            display_name=form.display_name.data,
            phone=form.phone.data,
            password=generate_password_hash(form.password.data),
            referral_code=code,
            referred_by=referrer.referral_code if referrer else None,
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Account created! Please activate your account to start earning.", "success")
        return redirect(url_for("dashboard.activate"))

    return render_template("auth/signup.html", form=form, ref_code=ref_code)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.display_name}!", "success")
            if user.is_super_admin:
                return redirect(next_page or url_for("super_admin.index"))
            elif user.is_admin:
                return redirect(next_page or url_for("admin.index"))
            else:
                return redirect(next_page or url_for("dashboard.index"))
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
