import sqlite3

import pytest
from flask import g, url_for

from app import app as flask_app
import database.db as database
import database.queries as queries


@pytest.fixture
def delete_client(tmp_path, monkeypatch):
    database_path = tmp_path / "delete-expense-test.db"

    def get_test_db():
        if "db" not in g:
            g.db = sqlite3.connect(database_path)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    monkeypatch.setattr(database, "get_db", get_test_db)
    monkeypatch.setattr(queries, "get_db", get_test_db)
    monkeypatch.setitem(flask_app.config, "TESTING", True)

    with flask_app.app_context():
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
            VALUES (?, ?, ?, ?, ?, ?),
                   (?, ?, ?, ?, ?, ?),
                   (?, ?, ?, ?, ?, ?)
            """,
            (
                101, 1, 50.0, "Food", "Original lunch", "2026-10-01",
                102, 2, 75.5, "Bills", "Other user's expense", "2026-10-02",
                103, 1, 20.0, "Transport", "Owner's other expense", "2026-10-03",
            ),
        )
        database.get_db().commit()

    with flask_app.test_client() as client:
        yield client


def _url(app, endpoint, **values):
    with app.test_request_context():
        return url_for(endpoint, **values)


def _log_in_as(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def _expense_ids():
    with flask_app.app_context():
        rows = database.get_db().execute(
            "SELECT id FROM expenses ORDER BY id"
        ).fetchall()
    return [row["id"] for row in rows]


class TestDeleteExpenseRoutes:
    def test_unauthenticated_get_and_post_redirect_to_login_without_deleting(
        self, delete_client
    ):
        for response in (
            delete_client.get(_url(flask_app, "delete_expense", id=101)),
            delete_client.post(_url(flask_app, "delete_expense", id=101)),
        ):
            assert response.status_code == 302, "Guests should be redirected to login"
            assert response.headers["Location"].endswith(
                _url(flask_app, "login")
            ), "The redirect should lead to the login page"

        assert 101 in _expense_ids(), "Unauthenticated requests must not delete expenses"

    def test_get_shows_confirmation_details_and_leaves_expense_intact(
        self, delete_client
    ):
        _log_in_as(delete_client, 1)

        response = delete_client.get(_url(flask_app, "delete_expense", id=101))

        assert response.status_code == 200, "The owner's confirmation page should render"
        html = response.get_data(as_text=True)
        assert "Original lunch" in html
        assert "Food" in html
        assert 'method="post"' in html.lower(), "Confirmation must submit using POST"
        assert (
            f'action="{_url(flask_app, "delete_expense", id=101)}"' in html
        ), "The confirmation form should target this expense's delete route"
        assert (
            f'href="{_url(flask_app, "profile")}"' in html
        ), "The confirmation page should offer a link back to the profile"
        assert 101 in _expense_ids(), "Displaying confirmation must not delete the expense"

    @pytest.mark.parametrize(
        "expense_id",
        [102, 999],
        ids=["another-users-expense", "missing-expense"],
    )
    def test_get_returns_404_for_foreign_or_missing_expense(
        self, delete_client, expense_id
    ):
        _log_in_as(delete_client, 1)

        response = delete_client.get(
            _url(flask_app, "delete_expense", id=expense_id)
        )

        assert response.status_code == 404, (
            "Foreign and nonexistent expenses should both be hidden"
        )

    @pytest.mark.parametrize(
        "expense_id",
        [102, 999],
        ids=["another-users-expense", "missing-expense"],
    )
    def test_post_returns_404_for_foreign_or_missing_expense(
        self, delete_client, expense_id
    ):
        _log_in_as(delete_client, 1)

        response = delete_client.post(
            _url(flask_app, "delete_expense", id=expense_id)
        )

        assert response.status_code == 404, (
            "A user must not delete a foreign or nonexistent expense"
        )
        assert _expense_ids() == [101, 102, 103], (
            "A rejected deletion must leave every expense intact"
        )

    def test_post_deletes_only_selected_owned_expense_and_shows_success_feedback(
        self, delete_client
    ):
        _log_in_as(delete_client, 1)

        response = delete_client.post(
            _url(flask_app, "delete_expense", id=101),
            data={"user_id": "2"},
        )

        assert response.status_code == 302, "A successful deletion should redirect"
        assert response.headers["Location"].endswith(
            _url(flask_app, "profile")
        ), "A successful deletion should redirect to the profile"
        assert _expense_ids() == [102, 103], (
            "Only the selected expense should be deleted; other records must remain"
        )

        profile_response = delete_client.get(_url(flask_app, "profile"))
        assert profile_response.status_code == 200
        profile_html = profile_response.get_data(as_text=True).lower()
        assert "success" in profile_html or "delet" in profile_html, (
            "The redirected profile should display visible deletion success feedback"
        )
