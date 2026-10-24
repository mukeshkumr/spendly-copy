"""Tests for inclusive profile date-range filtering."""

import re
import sqlite3
import uuid
from datetime import date

import pytest
from flask import g

from database import queries


@pytest.fixture
def date_filter_database(monkeypatch):
    """Provide a shared in-memory database for query helpers and app routes."""
    database_uri = (
        f"file:date-filter-tests-{uuid.uuid4().hex}?mode=memory&cache=shared"
    )
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
        VALUES (1, 'Filter User', 'filter@example.com', '2026-01-14 12:00:00');
        """
    )
    anchor.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, 10.00, "Food", "Start boundary", "2026-10-10"),
            (1, 20.00, "Bills", "Inside range", "2026-10-12"),
            (1, 30.00, "Bills", "End boundary", "2026-10-15"),
            (1, 40.00, "Food", "After range", "2026-10-16"),
            (1, 50.00, "Other", "Older", "2026-10-09"),
        ],
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
    yield
    anchor.close()


@pytest.fixture
def authenticated_client(date_filter_database):
    from app import app

    with app.test_client() as client:
        with client.session_transaction() as user_session:
            user_session["user_id"] = 1
        yield client


def test_profile_queries_apply_inclusive_bounds_to_all_sections(
    date_filter_database,
):
    from app import app

    with app.app_context():
        stats = queries.get_summary_stats(1, "2026-10-10", "2026-10-15")
        transactions = queries.get_recent_transactions(
            1, start_date="2026-10-10", end_date="2026-10-15"
        )
        categories = queries.get_category_breakdown(
            1, "2026-10-10", "2026-10-15"
        )

    assert stats == {
        "total_spent": 60.0,
        "transaction_count": 3,
        "top_category": "Bills",
    }
    assert [transaction["date"] for transaction in transactions] == [
        "2026-10-15",
        "2026-10-12",
        "2026-10-10",
    ]
    assert {category["name"]: category["amount"] for category in categories} == {
        "Bills": 50.0,
        "Food": 10.0,
    }
    assert sum(category["pct"] for category in categories) == 100


@pytest.mark.parametrize(
    ("query", "expected_total", "expected_count"),
    [
        ("?start_date=2026-10-12", 90.0, 3),
        ("?end_date=2026-10-12", 80.0, 3),
    ],
)
def test_profile_route_accepts_single_date_bound(
    authenticated_client, query, expected_total, expected_count
):
    response = authenticated_client.get(f"/profile{query}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"₹{expected_total:.2f}" in page
    assert f">{expected_count}<" in page


def test_profile_route_filters_data_and_retains_selected_dates(
    authenticated_client,
):
    response = authenticated_client.get(
        "/profile?start_date=2026-10-10&end_date=2026-10-15"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "value=\"2026-10-10\"" in page
    assert "value=\"2026-10-15\"" in page
    assert "2026-10-10 to 2026-10-15" in page
    assert "₹60.00" in page
    assert "Start boundary" in page
    assert "End boundary" in page
    assert "After range" not in page
    assert "Older" not in page
    assert page.count('class="category-list-item"') == 2


@pytest.mark.parametrize(
    ("preset", "label"),
    [
        ("all_time", "All Time"),
        ("this_month", "This Month"),
        ("last_3_months", "Last 3 Months"),
        ("last_6_months", "Last 6 Months"),
    ],
)
def test_profile_route_renders_selected_quick_filter(
    authenticated_client, preset, label
):
    response = authenticated_client.get(f"/profile?preset={preset}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    buttons = re.findall(
        r"<button\b([^>]*)>(.*?)</button>", page, flags=re.DOTALL
    )
    active_labels = [
        button_label.strip()
        for attributes, button_label in buttons
        if 'aria-pressed="true"' in attributes
    ]
    assert active_labels == [label]

    if preset != "all_time":
        assert f'value="{date.today().isoformat()}"' in page


@pytest.mark.parametrize(
    ("preset", "label", "months_back"),
    [
        ("this_month", "This Month", None),
        ("last_3_months", "Last 3 Months", 3),
        ("last_6_months", "Last 6 Months", 6),
    ],
)
def test_quick_filter_uses_expected_inclusive_dates(preset, label, months_back):
    from app import _profile_date_filter, _subtract_months, app

    today = date.today()
    start_date = (
        today.replace(day=1)
        if months_back is None
        else _subtract_months(today, months_back)
    )
    with app.test_request_context(f"/profile?preset={preset}"):
        assert _profile_date_filter() == (
            start_date.isoformat(),
            today.isoformat(),
            preset,
            label,
        )


def test_clearing_filter_restores_all_time_results(authenticated_client):
    filtered = authenticated_client.get("/profile?start_date=2026-10-10")
    filtered_page = filtered.get_data(as_text=True)
    assert 'name="preset"' in filtered_page
    assert 'value="all_time"' in filtered_page

    all_time = authenticated_client.get("/profile")
    all_time_page = all_time.get_data(as_text=True)

    assert 'value="custom"' in filtered_page
    assert "₹150.00" in all_time_page
    assert "All Time" in all_time_page
    buttons = re.findall(
        r"<button\b([^>]*)>(.*?)</button>", all_time_page, flags=re.DOTALL
    )
    assert [
        button_label.strip()
        for attributes, button_label in buttons
        if 'aria-pressed="true"' in attributes
    ] == ["All Time"]


@pytest.mark.parametrize(
    "query",
    [
        "?start_date=2026-02-30",
        "?end_date=20261015",
        "?start_date=2026-10-16&end_date=2026-10-15",
    ],
)
def test_invalid_date_filter_returns_clear_bad_request(
    authenticated_client, query
):
    response = authenticated_client.get(f"/profile{query}")

    assert response.status_code == 400
    assert "date" in response.get_data(as_text=True).lower()


def test_guest_with_invalid_dates_still_redirects_to_login(date_filter_database):
    from app import app

    response = app.test_client().get("/profile?start_date=not-a-date")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_unfiltered_query_helpers_preserve_all_time_behavior(date_filter_database):
    from app import app

    with app.app_context():
        stats = queries.get_summary_stats(1)
        transactions = queries.get_recent_transactions(1)
        categories = queries.get_category_breakdown(1)

    assert stats["total_spent"] == pytest.approx(150.0)
    assert stats["transaction_count"] == 5
    assert len(transactions) == 5
    assert sum(category["pct"] for category in categories) == 100


def test_recent_transactions_keeps_default_ten_item_limit(date_filter_database):
    from app import app

    with app.app_context():
        db = queries.get_db()
        db.executemany(
            """
            INSERT INTO expenses (user_id, amount, category, description, date)
            VALUES (1, 1, 'Food', 'Extra', ?)
            """,
            [(f"2026-11-{day:02d}",) for day in range(1, 9)],
        )
        db.commit()

        transactions = queries.get_recent_transactions(1)

    assert len(transactions) == 10
