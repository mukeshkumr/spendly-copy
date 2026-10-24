"""Focused tests for the profile-page query helpers and route."""

import sqlite3
import uuid

import pytest
from flask import Flask, g

from database import queries
from database.db import init_app


EXPENSES = [
    (1, 129.24, "Bills", "Electric bill", "2026-10-10"),
    (1, 12.00, "Transport", "Bus fare", "2026-10-16"),
    (1, 45.50, "Food", "Grocery shopping", "2026-10-15"),
    (1, 25.00, "Entertainment", "Movie tickets", "2026-10-12"),
    (1, 15.75, "Other", "Lunch delivery", "2026-10-18"),
    (1, 35.00, "Shopping", "Clothing purchase", "2026-10-14"),
    (1, 18.50, "Health", "Pharmacy visit", "2026-10-17"),
    (1, 65.25, "Food", "Concert tickets", "2026-10-11"),
]


@pytest.fixture
def profile_database(monkeypatch):
    """Provide an isolated shared in-memory SQLite database."""
    database_uri = f"file:profile-tests-{uuid.uuid4().hex}?mode=memory&cache=shared"
    anchor = sqlite3.connect(database_uri, uri=True)
    anchor.row_factory = sqlite3.Row
    anchor.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at DATETIME
        );
        CREATE TABLE expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO users (id, name, email, created_at)
        VALUES
            (1, 'Demo User', 'demo@spendly.com', '2026-01-14 12:00:00'),
            (2, 'New User', 'new@spendly.com', '2026-02-01 09:00:00');
        """
    )
    anchor.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        EXPENSES,
    )
    anchor.commit()

    def get_test_db():
        if "db" not in g:
            connection = sqlite3.connect(
                database_uri,
                uri=True,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            connection.row_factory = sqlite3.Row
            g.db = connection
        return g.db

    monkeypatch.setattr(queries, "get_db", get_test_db)
    query_app = Flask(__name__)
    init_app(query_app)
    yield query_app
    anchor.close()


def test_get_user_by_id_returns_formatted_profile_and_none_for_missing(
    profile_database,
):
    with profile_database.app_context():
        assert queries.get_user_by_id(1) == {
            "name": "Demo User",
            "email": "demo@spendly.com",
            "member_since": "January 2026",
        }
        assert queries.get_user_by_id(999) is None


def test_get_summary_stats_with_and_without_expenses(profile_database):
    with profile_database.app_context():
        stats = queries.get_summary_stats(1)
        empty_stats = queries.get_summary_stats(2)

    assert stats["total_spent"] == pytest.approx(346.24)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"
    assert empty_stats == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_get_recent_transactions_returns_newest_first_and_empty_for_new_user(
    profile_database,
):
    with profile_database.app_context():
        transactions = queries.get_recent_transactions(1)
        empty_transactions = queries.get_recent_transactions(2)

    assert [item["date"] for item in transactions] == [
        "2026-10-18",
        "2026-10-17",
        "2026-10-16",
        "2026-10-15",
        "2026-10-14",
        "2026-10-12",
        "2026-10-11",
        "2026-10-10",
    ]
    assert transactions[0] == {
        "date": "2026-10-18",
        "description": "Lunch delivery",
        "category": "Other",
        "amount": 15.75,
    }
    assert empty_transactions == []


def test_get_category_breakdown_percentages_total_100(profile_database):
    with profile_database.app_context():
        categories = queries.get_category_breakdown(1)
        empty_categories = queries.get_category_breakdown(2)

    assert categories[0]["name"] == "Bills"
    assert [item["amount"] for item in categories] == sorted(
        (item["amount"] for item in categories), reverse=True
    )
    assert len(categories) == 7
    assert all(isinstance(item["pct"], int) for item in categories)
    assert sum(item["pct"] for item in categories) == 100
    assert empty_categories == []


def test_profile_route_redirects_guests_and_renders_live_profile_data(
    profile_database,
):
    from app import app as spendly_app

    with spendly_app.test_client() as client:
        response = client.get("/profile")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

        with client.session_transaction() as session:
            session["user_id"] = 1

        response = client.get("/profile")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Demo User" in page
    assert "demo@spendly.com" in page
    assert "₹346.24" in page
    assert "8" in page
    assert "Bills" in page
    assert page.index("Lunch delivery") < page.index("Pharmacy visit")
    assert page.count("class=\"category-list-item\"") == 7

    with client.session_transaction() as session:
        session["user_id"] = 2

    empty_page = client.get("/profile").get_data(as_text=True)
    assert "New User" in empty_page
    assert "₹0.00" in empty_page
    assert "0 items" in empty_page
    assert 'class="category-list-item"' not in empty_page
