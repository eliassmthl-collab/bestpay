#!/usr/bin/env python3
"""
BestPay Database Seed Script (PostgreSQL)
Run: python seed.py
"""

from app import create_app, db
from app.models import User, SiteSetting
from werkzeug.security import generate_password_hash

app = create_app()


def seed():
    with app.app_context():
        print("🌱 Seeding BestPay PostgreSQL database…")

        # ── Site Settings ──────────────────────────────────────────────────
        settings = {
            "bank_name": "GTBank",
            "account_number": "0123456789",
            "account_name": "BestPay Enterprises",
            "platform_name": "BestPay",
            "registration_fee": "1000",
            "milestone_3_bonus": "2000",      # one-time bonus at 3 referrals
            "per_referral_bonus": "500",       # per-referral bonus for refs 4–20
            "withdrawal_tax_rate": "0.10",     # silent 10% withdrawal tax
        }
        for key, value in settings.items():
            if not SiteSetting.query.filter_by(key=key).first():
                db.session.add(SiteSetting(key=key, value=value))
        db.session.commit()
        print("  ✓ Site settings seeded")

        # ── Super Admin ────────────────────────────────────────────────────
        if not User.query.filter_by(email="super@bestpay.com").first():
            db.session.add(User(
                email="super@bestpay.com",
                display_name="Super Admin",
                phone="08000000000",
                password=generate_password_hash("admin123"),
                referral_code="SUPERADM",
                is_super_admin=True,
                is_admin=True,
                is_approved=True,
                registration_fee_paid=True,
            ))
            print("  ✓ super@bestpay.com / admin123")

        # ── Admins ────────────────────────────────────────────────────────
        for email, name, code in [
            ("best@bestpay.com",  "Best Admin",  "BESTADM1"),
            ("elias@bestpay.com", "Elias Admin", "ELIADM1"),
        ]:
            if not User.query.filter_by(email=email).first():
                db.session.add(User(
                    email=email,
                    display_name=name,
                    phone="08000000001",
                    password=generate_password_hash("admin123"),
                    referral_code=code,
                    is_admin=True,
                    is_approved=True,
                    registration_fee_paid=True,
                ))
                print(f"  ✓ {email} / admin123")

        db.session.commit()

        print("  ✓ No test users seeded (clean slate for real users)")

        print("\n" + "═" * 50)
        print("✅  BestPay seeded successfully! (PostgreSQL)")
        print("═" * 50)
        print("\n📋 Login Credentials:")
        print("   super@bestpay.com  → admin123  (super admin)")
        print("   best@bestpay.com   → admin123  (admin)")
        print("   elias@bestpay.com  → admin123  (admin)")
        print("\n🚀  Run the app:  python run.py")
        print("   → http://localhost:5000\n")


if __name__ == "__main__":
    seed()
