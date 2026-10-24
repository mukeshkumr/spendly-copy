import sqlite3

import pytest
from flask import g

from app import app
import database.db as database
import database.queries as queries


@pytest.fixture
def expense_client(tmp_path, monkeypatch):
    database_path = tmp_path / "expenses-test.db"

    def get_test_db():
        if "db" not in g:
            g.db = sqlite3.connect(
                database_path,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    monkeypatch.setattr(database, "get_db", get_test_db)
    monkeypatch.setattr(queries, "get_db", get_test_db)
    monkeypatch.setitem(app.config, "TESTING", True)

    with app.app_context():
        database.init_db()
        database.get_db().execute(
            """
            INSERT INTO users (id, name, email, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (1, "Expense Tester", "expense@example.com", "not-used"),
        )
        database.get_db().commit()

    with app.test_client() as client:
        yield client


def test_add_expense_requires_login(expense_client):
    for response in (
        expense_client.get("/expenses/add"),
        expense_client.post("/expenses/add", data={"amount": "10"}),
    ):
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")

    with app.app_context():
        count = database.get_db().execute(
            "SELECT COUNT(*) AS count FROM expenses"
        ).fetchone()["count"]
    assert count == 0


def test_add_expense_form_renders_for_logged_in_user(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.get("/expenses/add")

    assert response.status_code == 200
    assert b"Add an expense" in response.data
    assert b"Entertainment" in response.data


def test_valid_expense_is_saved_for_logged_in_user(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/add",
        data={
            "amount": "123.45",
            "category": "Food",
            "date": "2026-10-24",
            "description": "Dinner",
            "user_id": "999",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    with app.app_context():
        expense = database.get_db().execute(
            "SELECT user_id, amount, category, description, date FROM expenses"
        ).fetchone()
    assert expense["user_id"] == 1
    assert expense["amount"] == 123.45
    assert expense["category"] == "Food"
    assert expense["description"] == "Dinner"
    assert expense["date"] == "2026-10-24"

    profile_response = expense_client.get("/profile")
    assert profile_response.status_code == 200
    assert b"Dinner" in profile_response.data
    assert b"\xe2\x82\xb9" in profile_response.data


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "0"),
        ("amount", "not-a-number"),
        ("amount", "1e9999"),
        ("date", "2026-02-30"),
        ("category", "Unknown"),
    ],
)
def test_invalid_expense_is_not_saved(expense_client, field, value):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1
    data = {
        "amount": "10.00",
        "category": "Food",
        "date": "2026-10-24",
        "description": "",
    }
    data[field] = value

    response = expense_client.post("/expenses/add", data=data)

    assert response.status_code == 400
    assert b"valid" in response.data.lower() or b"greater than zero" in response.data.lower()
    with app.app_context():
        count = database.get_db().execute(
            "SELECT COUNT(*) AS count FROM expenses"
        ).fetchone()["count"]
    assert count == 0


def test_expense_description_is_optional(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/add",
        data={
            "amount": "10.00",
            "category": "Other",
            "date": "2026-10-24",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        expense = database.get_db().execute(
            "SELECT description FROM expenses"
        ).fetchone()
    assert expense["description"] is None
