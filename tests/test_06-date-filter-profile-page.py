import importlib
import sqlite3
from html.parser import HTMLParser

import pytest
from flask import g


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Build an isolated SQLite database and point the app queries at it."""
    import database.db as database
    import database.queries as queries

    database_path = tmp_path / "profile-date-filter.sqlite"

    # Create the schema before importing the application so this fixture also
    # works when another test has already imported the Flask app.
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE expenses (
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
    connection.commit()
    connection.close()

    def get_test_db():
        if "db" not in g:
            g.db = sqlite3.connect(database_path)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    monkeypatch.setattr(database, "get_db", get_test_db)
    monkeypatch.setattr(queries, "get_db", get_test_db)
    flask_app = importlib.import_module("app").app
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret")

    # Avoid any development seed data created during the app's first import.
    connection = sqlite3.connect(database_path)
    connection.execute("DELETE FROM expenses")
    connection.execute("DELETE FROM users")
    cursor = connection.execute(
        """
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
        """,
        ("Date Filter User", "date-filter@example.test", "unused-test-hash"),
    )
    user_id = cursor.lastrowid
    other_cursor = connection.execute(
        """
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
        """,
        ("Other User", "other@example.test", "unused-test-hash"),
    )
    other_user_id = other_cursor.lastrowid
    expenses = [
        (user_id, 100.00, "Food", "Before range", "2025-01-09"),
        (user_id, 10.00, "Food", "Start boundary", "2025-01-10"),
        (user_id, 20.00, "Transport", "Inside range", "2025-01-15"),
        (user_id, 30.00, "Food", "End boundary", "2025-01-20"),
        (user_id, 200.00, "Entertainment", "After range", "2025-01-21"),
        (other_user_id, 900.00, "Bills", "Other user's expense", "2025-01-15"),
    ]
    connection.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        expenses,
    )
    connection.commit()
    connection.close()

    flask_app.config["DATE_FILTER_TEST_USER_ID"] = user_id
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    """A test client with the fixture's user already authenticated."""
    with client.session_transaction() as user_session:
        user_session["user_id"] = app.config["DATE_FILTER_TEST_USER_ID"]
    return client


class _ClearLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.inputs = {}
        self._current_href = None
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name"):
            self.inputs[attributes["name"]] = attributes.get("value", "")
        if tag == "a":
            self._current_href = attributes.get("href")
            self._current_text = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._current_href is not None:
            self.links.append((self._current_href, "".join(self._current_text)))
            self._current_href = None
            self._current_text = []


def test_profile_without_dates_shows_all_time_data_by_default(auth_client):
    response = auth_client.get("/profile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200, "Expected the logged-in profile page"
    assert "₹360.00" in html, "Default summary should include all five expenses"
    assert ">5<" in html, "Default summary should show all five transactions"
    for description in (
        "Before range",
        "Start boundary",
        "Inside range",
        "End boundary",
        "After range",
    ):
        assert description in html, f"Expected all-time transaction {description!r}"
    assert "Other user's expense" not in html, "Profile data must remain user-scoped"


def test_profile_inclusive_range_filters_summary_transactions_and_categories(
    auth_client,
):
    response = auth_client.get(
        "/profile?start_date=2025-01-10&end_date=2025-01-20"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200, "A valid inclusive range should render"
    assert "₹60.00" in html, "Summary total should include only range expenses"
    assert ">3<" in html, "Summary count should include both boundary dates"
    assert "Start boundary" in html, "The start date should be included"
    assert "Inside range" in html, "An expense inside the range should be included"
    assert "End boundary" in html, "The end date should be included"
    assert "Before range" not in html, "Expenses before the range must be excluded"
    assert "After range" not in html, "Expenses after the range must be excluded"
    assert "Food" in html and "Transport" in html, (
        "Category breakdown should include categories in the selected range"
    )
    assert "Entertainment" not in html, (
        "Category breakdown must exclude categories outside the selected range"
    )
    assert "₹40.00" in html and "₹20.00" in html, (
        "Category totals should use only the selected expenses"
    )
    assert "Other user's expense" not in html, "Date filtering must remain user-scoped"


def test_profile_start_only_applies_inclusive_lower_bound_to_all_sections(auth_client):
    response = auth_client.get("/profile?start_date=2025-01-20")
    html = response.get_data(as_text=True)

    assert response.status_code == 200, "A valid start-only filter should render"
    assert "₹230.00" in html, "Start-only summary should include dates on or after start"
    assert ">2<" in html, "Start-only transaction count should reflect its lower bound"
    assert "End boundary" in html, "The start-only lower bound should be inclusive"
    assert "After range" in html, "Later expenses should remain in the result"
    assert "Before range" not in html and "Inside range" not in html, (
        "Earlier expenses must be excluded from every profile section"
    )
    assert "Food" not in html, "Categories before the lower bound must not leak into breakdown"


def test_profile_end_only_applies_inclusive_upper_bound_to_all_sections(auth_client):
    response = auth_client.get("/profile?end_date=2025-01-10")
    html = response.get_data(as_text=True)

    assert response.status_code == 200, "A valid end-only filter should render"
    assert "₹110.00" in html, "End-only summary should include dates on or before end"
    assert ">2<" in html, "End-only transaction count should reflect its upper bound"
    assert "Before range" in html, "Earlier expenses should remain in the result"
    assert "Start boundary" in html, "The end-only upper bound should be inclusive"
    assert "Inside range" not in html and "End boundary" not in html, (
        "Later expenses must be excluded from every profile section"
    )
    assert "Transport" not in html and "Entertainment" not in html, (
        "Categories after the upper bound must not appear in the breakdown"
    )


def test_profile_retains_selected_dates_and_clear_link_restores_all_time(auth_client):
    filtered = auth_client.get(
        "/profile?start_date=2025-01-10&end_date=2025-01-20"
    )
    html = filtered.get_data(as_text=True)

    assert filtered.status_code == 200, "Expected the selected range to render"
    parser = _ClearLinkParser()
    parser.feed(html)
    assert parser.inputs.get("start_date") == "2025-01-10", (
        "The selected start date should remain visible in its input"
    )
    assert parser.inputs.get("end_date") == "2025-01-20", (
        "The selected end date should remain visible in its input"
    )
    clear_links = [
        href for href, text in parser.links if "clear" in text.strip().lower()
    ]
    assert clear_links, "The filter form should provide a clear-filter link"
    assert all("start_date=" not in href and "end_date=" not in href for href in clear_links), (
        "A clear-filter link should not retain either selected date"
    )

    cleared = auth_client.get("/profile")
    cleared_html = cleared.get_data(as_text=True)
    assert cleared.status_code == 200, "Clearing the filter should return to the profile"
    assert "₹360.00" in cleared_html, "Clearing should restore all-time summary data"
    assert "Before range" in cleared_html and "After range" in cleared_html, (
        "Clearing should restore transactions outside the selected period"
    )


@pytest.mark.parametrize(
    ("query", "message_terms"),
    [
        ("start_date=not-a-date", ("date", "valid")),
        ("end_date=2025-02-30", ("date", "valid")),
        ("start_date=2025-1-10", ("date", "valid")),
    ],
)
def test_profile_malformed_date_returns_clear_client_error_without_fallback(
    auth_client, query, message_terms
):
    response = auth_client.get(f"/profile?{query}")
    body = response.get_data(as_text=True).lower()

    assert response.status_code == 400, "Malformed dates should be rejected as client errors"
    assert all(term in body for term in message_terms), (
        "The error response should clearly explain that the supplied date is invalid"
    )
    assert "₹360.00" not in body, "Invalid filters must not render unfiltered profile data"
    assert "Before range" not in body, "Invalid filters must not fall back to transactions"


def test_profile_reversed_date_range_returns_clear_client_error(auth_client):
    response = auth_client.get(
        "/profile?start_date=2025-01-21&end_date=2025-01-10"
    )
    body = response.get_data(as_text=True).lower()

    assert response.status_code == 400, "A reversed range should be rejected"
    assert "start" in body and "end" in body, (
        "The error should explain the invalid ordering of the date bounds"
    )
    assert "₹360.00" not in body, "A reversed range must not fall back to all-time results"


def test_profile_unauthenticated_request_redirects_even_with_date_arguments(client):
    response = client.get(
        "/profile?start_date=malformed&end_date=also-malformed"
    )

    assert response.status_code == 302, "Unauthenticated profile access should redirect"
    assert response.headers["Location"].endswith("/login"), (
        "Date arguments must not bypass the existing login guard"
    )


def test_profile_query_helpers_without_date_bounds_keep_all_time_behavior(app):
    from database.queries import (
        get_category_breakdown,
        get_recent_transactions,
        get_summary_stats,
    )

    user_id = app.config["DATE_FILTER_TEST_USER_ID"]
    with app.app_context():
        summary = get_summary_stats(user_id)
        transactions = get_recent_transactions(user_id)
        categories = get_category_breakdown(user_id)

    assert summary == {
        "total_spent": 360.0,
        "transaction_count": 5,
        "top_category": "Entertainment",
    }, "Omitted bounds should preserve all-time summary behavior"
    assert len(transactions) == 5, "Omitted bounds should return all recent transactions"
    assert {transaction["description"] for transaction in transactions} == {
        "Before range",
        "Start boundary",
        "Inside range",
        "End boundary",
        "After range",
    }, "Omitted bounds should preserve all-time transaction results"
    assert {category["name"]: category["amount"] for category in categories} == {
        "Food": 140.0,
        "Transport": 20.0,
        "Entertainment": 200.0,
    }, "Omitted bounds should preserve all-time category totals"
