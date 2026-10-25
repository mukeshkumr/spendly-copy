import sqlite3

import pytest
from flask import g

from app import app
import database.db as database
import database.queries as queries


@pytest.fixture
def expense_client(tmp_path, monkeypatch):
    database_path = tmp_path / "edit-expense-test.db"

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
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (
                1,
                "Owner User",
                "owner@example.com",
                "not-used",
                2,
                "Other User",
                "other@example.com",
                "not-used",
            ),
        )
        database.get_db().execute(
            """
            INSERT INTO expenses (id, user_id, amount, category, description, date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (101, 1, 50.0, "Food", "Lunch", "2026-10-01"),
        )
        database.get_db().execute(
            """
            INSERT INTO expenses (id, user_id, amount, category, description, date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (102, 2, 75.5, "Bills", "Power bill", "2026-10-02"),
        )
        database.get_db().commit()

    with app.test_client() as client:
        yield client


def test_get_expense_by_id_returns_row_for_owner(expense_client):
    with app.app_context():
        expense = queries.get_expense_by_id(101, 1)
    assert expense is not None
    assert expense["description"] == "Lunch"
    assert expense["category"] == "Food"


def test_get_expense_by_id_returns_none_for_other_user(expense_client):
    with app.app_context():
        assert queries.get_expense_by_id(101, 2) is None


def test_get_expense_by_id_returns_none_for_missing_expense(expense_client):
    with app.app_context():
        assert queries.get_expense_by_id(999, 1) is None


def test_update_expense_updates_matching_row(expense_client):
    with app.app_context():
        rows_updated = queries.update_expense(101, 1, 99.0, "Transport", "2026-10-15", "Commute")
        expense = database.get_db().execute(
            "SELECT amount, category, date, description FROM expenses WHERE id = ?",
            (101,),
        ).fetchone()
    assert rows_updated == 1
    assert expense["amount"] == 99.0
    assert expense["category"] == "Transport"
    assert expense["date"] == "2026-10-15"
    assert expense["description"] == "Commute"


def test_update_expense_does_nothing_for_wrong_user(expense_client):
    with app.app_context():
        rows_updated = queries.update_expense(101, 2, 20.0, "Bills", "2026-10-10", "Attempt")
        expense = database.get_db().execute(
            "SELECT amount, category, description, date FROM expenses WHERE id = ?",
            (101,),
        ).fetchone()
    assert rows_updated == 0
    assert expense["amount"] == 50.0
    assert expense["category"] == "Food"


def test_edit_route_requires_login(expense_client):
    for response in (
        expense_client.get("/expenses/101/edit"),
        expense_client.post("/expenses/101/edit", data={"amount": "10", "category": "Food", "date": "2026-10-20", "description": ""}),
    ):
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")


def test_edit_route_renders_prepopulated_form_for_owner(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.get("/expenses/101/edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Edit expense" in html
    assert 'value="50.0"' in html or 'value="50.00"' in html or 'value="50"' in html
    assert "Lunch" in html
    assert 'value="Food"' in html or "Food" in html
    assert 'selected' in html


def test_edit_route_returns_404_for_other_user_expense(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.get("/expenses/102/edit")
    assert response.status_code == 404


def test_edit_route_returns_404_for_missing_expense(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.get("/expenses/999/edit")
    assert response.status_code == 404


def test_edit_route_updates_expense_for_valid_post(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/101/edit",
        data={
            "amount": "99.50",
            "category": "Transport",
            "date": "2026-10-15",
            "description": "Updated trip",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")

    with app.app_context():
        expense = database.get_db().execute(
            "SELECT amount, category, date, description FROM expenses WHERE id = ?",
            (101,),
        ).fetchone()
    assert expense["amount"] == 99.5
    assert expense["category"] == "Transport"
    assert expense["date"] == "2026-10-15"
    assert expense["description"] == "Updated trip"


def test_edit_route_rejects_other_users_expense_on_post(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/102/edit",
        data={
            "amount": "25.00",
            "category": "Food",
            "date": "2026-10-20",
            "description": "Should fail",
        },
    )

    assert response.status_code == 404


def test_edit_route_re_renders_form_on_missing_amount(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/101/edit",
        data={
            "amount": "",
            "category": "Food",
            "date": "2026-10-20",
            "description": "Still here",
        },
    )

    assert response.status_code == 400
    assert b"greater than zero" in response.data.lower() or b"valid" in response.data.lower()


def test_edit_route_re_renders_form_on_invalid_amount(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/101/edit",
        data={
            "amount": "0",
            "category": "Food",
            "date": "2026-10-20",
            "description": "Zero",
        },
    )

    assert response.status_code == 400
    assert b"greater than zero" in response.data.lower() or b"valid" in response.data.lower()


def test_edit_route_re_renders_form_on_invalid_category(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/101/edit",
        data={
            "amount": "10.00",
            "category": "Nope",
            "date": "2026-10-20",
            "description": "Bad category",
        },
    )

    assert response.status_code == 400
    assert b"category" in response.data.lower()


def test_edit_route_re_renders_form_on_invalid_date(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/101/edit",
        data={
            "amount": "10.00",
            "category": "Food",
            "date": "2026-02-30",
            "description": "Wrong date",
        },
    )

    assert response.status_code == 400
    assert b"date" in response.data.lower()


def test_edit_route_updates_description_to_null_when_blank(expense_client):
    with expense_client.session_transaction() as session:
        session["user_id"] = 1

    response = expense_client.post(
        "/expenses/101/edit",
        data={
            "amount": "10.00",
            "category": "Food",
            "date": "2026-10-20",
            "description": "   ",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")

    with app.app_context():
        expense = database.get_db().execute(
            "SELECT description FROM expenses WHERE id = ?",
            (101,),
        ).fetchone()
    assert expense["description"] is None
