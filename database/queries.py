"""Profile-page queries backed by the application's SQLite database."""

from datetime import datetime
import math

from database.db import close_db, get_db


def _close_connection():
    """Close and remove the connection created for the current query."""
    close_db()


def _date_filter(start_date, end_date):
    """Return parameterized SQL and values for optional inclusive date bounds."""
    conditions = []
    parameters = []
    if start_date is not None:
        conditions.append("date >= ?")
        parameters.append(start_date)
    if end_date is not None:
        conditions.append("date <= ?")
        parameters.append(end_date)
    return "".join(" AND " + condition for condition in conditions), parameters


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


def get_summary_stats(user_id, start_date=None, end_date=None):
    """Return total spending, transaction count, and highest-spend category."""
    db = get_db()
    date_clause, date_parameters = _date_filter(start_date, end_date)
    parameters = (user_id, *date_parameters)
    try:
        totals = db.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total_spent,
                   COUNT(*) AS transaction_count
            FROM expenses
            WHERE user_id = ?
            """ + date_clause,
            parameters,
        ).fetchone()
        top_category = db.execute(
            """
            SELECT category
            FROM expenses
            WHERE user_id = ?
            """ + date_clause + """
            GROUP BY category
            ORDER BY SUM(amount) DESC, category ASC
            LIMIT 1
            """,
            parameters,
        ).fetchone()
        return {
            "total_spent": totals["total_spent"],
            "transaction_count": totals["transaction_count"],
            "top_category": top_category["category"] if top_category else "—",
        }
    finally:
        _close_connection()


def get_expense_by_id(expense_id, user_id):
    """Return a single expense for the given user, or None if not found."""
    db = get_db()
    try:
        row = db.execute(
            """
            SELECT *
            FROM expenses
            WHERE id = ? AND user_id = ?
            """,
            (expense_id, user_id),
        ).fetchone()
        return row
    finally:
        _close_connection()


def update_expense(expense_id, user_id, amount, category, expense_date, description):
    """Update an expense only when it belongs to the authenticated user."""
    db = get_db()
    try:
        cursor = db.execute(
            """
            UPDATE expenses
            SET amount = ?, category = ?, date = ?, description = ?
            WHERE id = ? AND user_id = ?
            """,
            (amount, category, expense_date, description, expense_id, user_id),
        )
        db.commit()
        return cursor.rowcount
    finally:
        _close_connection()


def get_recent_transactions(user_id, limit=10, start_date=None, end_date=None):
    """Return a user's latest transactions, with the newest date first."""
    db = get_db()
    date_clause, date_parameters = _date_filter(start_date, end_date)
    try:
        rows = db.execute(
            """
            SELECT id, date, description, category, amount
            FROM expenses
            WHERE user_id = ?
            """ + date_clause + """
            ORDER BY date DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, *date_parameters, limit),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "date": row["date"],
                "description": row["description"],
                "category": row["category"],
                "amount": row["amount"],
            }
            for row in rows
        ]
    finally:
        _close_connection()


def get_category_breakdown(user_id, start_date=None, end_date=None):
    """Return category totals and integer percentages totaling exactly 100."""
    db = get_db()
    date_clause, date_parameters = _date_filter(start_date, end_date)
    try:
        rows = db.execute(
            """
            SELECT category AS name, SUM(amount) AS amount
            FROM expenses
            WHERE user_id = ?
            """ + date_clause + """
            GROUP BY category
            ORDER BY amount DESC, name ASC
            """,
            (user_id, *date_parameters),
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
