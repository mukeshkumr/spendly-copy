"""SQLite database helpers for Spendly expense tracker."""
import os
import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    """Return a SQLite database connection.

    The connection is stored in the Flask application context and reused
    within a request. Foreign keys are enabled and row_factory is set
    to sqlite3.Row for dict-like access to columns.

    Returns:
        sqlite3.Connection: A database connection with row_factory and
            foreign keys enabled.
    """
    if "db" not in g:
        # Determine database path - use 'spendly.db' in project root
        db_path = os.path.join(current_app.root_path, 'spendly.db')
        g.db = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_=None):
    """Close the database connection stored in the application context.

    This function is registered with Flask's teardown_appcontext to ensure
    connections are properly closed after each request.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all database tables.

    This function creates the necessary tables for the Spendly application:
    - users: Stores user account information
    - expenses: Stores expense records linked to users
    """
    db = get_db()

    # Create users table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Create expenses table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )

    db.commit()


def seed_db():
    """Insert sample data for development and testing.

    This function adds:
    - A demo user account
    - 8 sample expense records for the user
    """
    db = get_db()

    # Check if data already exists
    user_count = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count > 0:
        return

    # Insert sample user
    db.execute(
        """
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
        """,
        (
            "Demo User",
            "demo@spendly.com",
            generate_password_hash("demo123")
        )
    )

    # Insert sample expenses (covering all categories)
    sample_expenses = [
        (1, 45.50, "Food", "Grocery shopping", "2026-10-15"),
        (1, 12.00, "Transport", "Bus fare", "2026-10-16"),
        (1, 89.99, "Bills", "Electric bill", "2026-10-10"),
        (1, 25.00, "Entertainment", "Movie tickets", "2026-10-12"),
        (1, 15.75, "Food", "Lunch delivery", "2026-10-18"),
        (1, 35.00, "Shopping", "Clothing purchase", "2026-10-14"),
        (1, 18.50, "Health", "Pharmacy visit", "2026-10-17"),
        (1, 65.25, "Entertainment", "Concert tickets", "2026-10-11"),
    ]

    db.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        sample_expenses,
    )

    db.commit()


def init_app(app):
    """Register database functions with the Flask app.

    This function should be called in the factory function to register
    teardown handlers and initialize the database.
    """
    app.teardown_appcontext(close_db)