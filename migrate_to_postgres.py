#!/usr/bin/env python3
"""
BestPay: SQLite → PostgreSQL Migration Script
Migrates all data from the local SQLite database into PostgreSQL.
SQLite file is NOT deleted — it remains as a backup.

Run: python migrate_to_postgres.py
"""

import sqlite3
import os
import sys
from datetime import datetime

# ── Setup ──────────────────────────────────────────────────────────────────────
SQLITE_PATH = os.path.join(os.path.dirname(__file__), "database.db")

if not os.path.exists(SQLITE_PATH):
    print(f"❌  SQLite database not found at {SQLITE_PATH}")
    sys.exit(1)

# Bootstrap Flask app (connects to PostgreSQL via DATABASE_URL or default)
from app import create_app, db
from app.models import (
    User, Transaction, Withdrawal, SupportTicket,
    TicketReply, SiteSetting, Notification
)

app = create_app()


def parse_dt(val):
    """Parse a datetime string from SQLite into a Python datetime."""
    if not val:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def migrate():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    with app.app_context():
        print("🔗  Connected to PostgreSQL.")
        print("🔨  Creating tables if they don't exist…")
        db.create_all()

        # ── Site Settings ──────────────────────────────────────────────────
        print("\n📋  Migrating site_settings…")
        cur.execute("SELECT * FROM site_settings")
        rows = cur.fetchall()
        count = 0
        for row in rows:
            if not SiteSetting.query.filter_by(key=row["key"]).first():
                db.session.add(SiteSetting(key=row["key"], value=row["value"]))
                count += 1
        db.session.commit()
        print(f"    ✓ {count} settings migrated ({len(rows) - count} already exist)")

        # ── Users ──────────────────────────────────────────────────────────
        print("\n👤  Migrating users…")
        cur.execute("SELECT * FROM users ORDER BY id")
        rows = cur.fetchall()
        count = 0
        id_map = {}  # old_id → new_id (in case of conflicts)
        for row in rows:
            existing = User.query.filter_by(email=row["email"]).first()
            if existing:
                id_map[row["id"]] = existing.id
                continue

            user = User(
                email=row["email"],
                display_name=row["display_name"],
                phone=row["phone"],
                password=row["password"],
                referral_code=row["referral_code"],
                referred_by=row["referred_by"],
                balance=row["balance"] or 0.0,
                registration_fee_paid=bool(row["registration_fee_paid"]),
                is_approved=bool(row["is_approved"]),
                payment_submitted=bool(row["payment_submitted"]),
                is_admin=bool(row["is_admin"]),
                is_super_admin=bool(row["is_super_admin"]),
                milestone_3_paid=bool(row["milestone_3_paid"]),
                created_at=parse_dt(row["created_at"]) or datetime.utcnow(),
            )
            db.session.add(user)
            db.session.flush()  # get user.id
            id_map[row["id"]] = user.id
            count += 1

        db.session.commit()
        print(f"    ✓ {count} users migrated ({len(rows) - count} already exist)")

        # ── Transactions ───────────────────────────────────────────────────
        print("\n💳  Migrating transactions…")
        cur.execute("SELECT * FROM transactions ORDER BY id")
        rows = cur.fetchall()
        count = 0
        txn_id_map = {}
        for row in rows:
            pg_user_id = id_map.get(row["user_id"])
            if not pg_user_id:
                continue
            pg_approved_by = id_map.get(row["approved_by"]) if row["approved_by"] else None

            txn = Transaction(
                user_id=pg_user_id,
                type=row["type"],
                amount=row["amount"],
                status=row["status"],
                description=row["description"],
                created_at=parse_dt(row["created_at"]) or datetime.utcnow(),
                approved_by=pg_approved_by,
            )
            db.session.add(txn)
            db.session.flush()
            txn_id_map[row["id"]] = txn.id
            count += 1

        db.session.commit()
        print(f"    ✓ {count} transactions migrated")

        # ── Withdrawals ────────────────────────────────────────────────────
        print("\n💸  Migrating withdrawals…")
        cur.execute("SELECT * FROM withdrawals ORDER BY id")
        rows = cur.fetchall()
        count = 0
        for row in rows:
            pg_user_id = id_map.get(row["user_id"])
            if not pg_user_id:
                continue
            pg_approved_by = id_map.get(row["approved_by"]) if row["approved_by"] else None

            wd = Withdrawal(
                user_id=pg_user_id,
                transaction_id=None,  # FK not available in old data
                amount=row["amount"],
                bank_name=row["bank_name"],
                account_number=row["account_number"],
                account_name=row["account_name"],
                status=row["status"],
                rejection_reason=row["rejection_reason"],
                created_at=parse_dt(row["created_at"]) or datetime.utcnow(),
                approved_at=parse_dt(row["approved_at"]),
                approved_by=pg_approved_by,
            )
            db.session.add(wd)
            count += 1

        db.session.commit()
        print(f"    ✓ {count} withdrawals migrated")

        # ── Support Tickets ────────────────────────────────────────────────
        print("\n🎫  Migrating support tickets…")
        cur.execute("SELECT * FROM support_tickets ORDER BY id")
        rows = cur.fetchall()
        count = 0
        ticket_id_map = {}
        for row in rows:
            pg_user_id = id_map.get(row["user_id"])
            if not pg_user_id:
                continue

            ticket = SupportTicket(
                user_id=pg_user_id,
                subject=row["subject"],
                message=row["message"],
                status=row["status"],
                created_at=parse_dt(row["created_at"]) or datetime.utcnow(),
            )
            db.session.add(ticket)
            db.session.flush()
            ticket_id_map[row["id"]] = ticket.id
            count += 1

        db.session.commit()
        print(f"    ✓ {count} support tickets migrated")

        # ── Ticket Replies ─────────────────────────────────────────────────
        print("\n💬  Migrating ticket replies…")
        cur.execute("SELECT * FROM ticket_replies ORDER BY id")
        rows = cur.fetchall()
        count = 0
        for row in rows:
            pg_ticket_id = ticket_id_map.get(row["ticket_id"])
            pg_user_id = id_map.get(row["user_id"])
            if not pg_ticket_id or not pg_user_id:
                continue

            reply = TicketReply(
                ticket_id=pg_ticket_id,
                user_id=pg_user_id,
                message=row["message"],
                created_at=parse_dt(row["created_at"]) or datetime.utcnow(),
            )
            db.session.add(reply)
            count += 1

        db.session.commit()
        print(f"    ✓ {count} ticket replies migrated")

        # ── Notifications ──────────────────────────────────────────────────
        print("\n🔔  Migrating notifications…")
        cur.execute("SELECT * FROM notifications ORDER BY id")
        rows = cur.fetchall()
        count = 0
        for row in rows:
            pg_user_id = id_map.get(row["user_id"])
            if not pg_user_id:
                continue

            notif = Notification(
                user_id=pg_user_id,
                message=row["message"],
                link=row["link"],
                is_read=bool(row["is_read"]),
                created_at=parse_dt(row["created_at"]) or datetime.utcnow(),
            )
            db.session.add(notif)
            count += 1

        db.session.commit()
        print(f"    ✓ {count} notifications migrated")

    conn.close()

    print("\n" + "═" * 50)
    print("✅  Migration complete!")
    print("═" * 50)
    print(f"\n📁  SQLite backup retained at: {SQLITE_PATH}")
    print("    It has NOT been deleted or modified.\n")


if __name__ == "__main__":
    migrate()
