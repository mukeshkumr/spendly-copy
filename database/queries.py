"""Profile-page queries backed by the application's SQLite database."""

from datetime import datetime
import math

from database.db import close_db, get_db


def _close_connection():
    """Close and remove the connection created for the current query."""
    close_db()


def get_user_by_id(user_id):
    """Return the public profile fields for a user, or None if absent."""
    db = get_db()
    try:
        row = db.execute(
            """
            SELECT name, email, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None

        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return {
            "name": row["name"],
            "email": row["email"],
            "member_since": created_at.strftime("%B %Y"),
        }
    finally:
        _close_connection()


def get_summary_stats(user_id):
    """Return total spending, transaction count, and highest-spend category."""
    db = get_db()
    try:
        totals = db.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total_spent,
                   COUNT(*) AS transaction_count
            FROM expenses
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        top_category = db.execute(
            """
            SELECT category
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY SUM(amount) DESC, category ASC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return {
            "total_spent": totals["total_spent"],
            "transaction_count": totals["transaction_count"],
            "top_category": top_category["category"] if top_category else "—",
        }
    finally:
        _close_connection()


def get_recent_transactions(user_id, limit=10):
    """Return a user's latest transactions, with the newest date first."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT date, description, category, amount
            FROM expenses
            WHERE user_id = ?
            ORDER BY date DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [
            {
                "date": row["date"],
                "description": row["description"],
                "category": row["category"],
                "amount": row["amount"],
            }
            for row in rows
        ]
    finally:
        _close_connection()


def get_category_breakdown(user_id):
    """Return category totals and integer percentages totaling exactly 100."""
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT category AS name, SUM(amount) AS amount
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY amount DESC, name ASC
            """,
            (user_id,),
        ).fetchall()
        if not rows:
            return []

        total = sum(row["amount"] for row in rows)
        if total <= 0:
            return [
                {
                    "name": row["name"],
                    "amount": row["amount"],
                    "pct": 100 if index == 0 else 0,
                }
                for index, row in enumerate(rows)
            ]
        breakdown = [
            {
                "name": row["name"],
                "amount": row["amount"],
                "pct": math.floor(row["amount"] * 100 / total + 0.5),
            }
            for row in rows
        ]
        breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)
        return breakdown
    finally:
        _close_connection()
