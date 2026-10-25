from html.parser import HTMLParser

import pytest
from flask import url_for

from app import app as flask_app
from database.db import close_db, create_expense, create_user, get_db, init_db
from database.queries import get_expense_by_id, update_expense


TEST_EMAIL = "edit-expense-test@example.com"
OTHER_EMAIL = "edit-expense-other@example.com"
TEST_PASSWORD = "test-password-123"


@pytest.fixture
def app():
    flask_app.config.update(
        {
            "TESTING": True,
            "DATABASE": ":memory:",
            "SECRET_KEY": "test-secret",
            "WTF_CSRF_ENABLED": False,
        }
    )
    with flask_app.app_context():
        init_db()
        db = get_db()
        db.execute("DELETE FROM users WHERE email IN (?, ?)", (TEST_EMAIL, OTHER_EMAIL))
        db.commit()
        close_db()

    yield flask_app

    with flask_app.app_context():
        db = get_db()
        db.execute("DELETE FROM users WHERE email IN (?, ?)", (TEST_EMAIL, OTHER_EMAIL))
        db.commit()
        close_db()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A client logged in as the test user's account."""
    registration = client.post(
        _url(client.application, "register"),
        data={
            "name": "Edit Expense Tester",
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "confirm_password": TEST_PASSWORD,
        },
    )
    assert registration.status_code == 302, "Expected test account registration"

    login = client.post(
        _url(client.application, "login"),
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert login.status_code == 302, "Expected test user to log in"
    return client


@pytest.fixture
def user_id(auth_client):
    with flask_app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT id FROM users WHERE email = ?", (TEST_EMAIL,)
        ).fetchone()
        close_db()
    assert row is not None, "Expected the authenticated test user in the database"
    return row["id"]


@pytest.fixture
def other_user_id(app):
    with app.app_context():
        other_id = create_user("Other Expense Owner", OTHER_EMAIL, TEST_PASSWORD)
        close_db()
    assert other_id is not None, "Expected a separate expense owner"
    return other_id


@pytest.fixture
def expense_id(app, user_id):
    with app.app_context():
        created_id = create_expense(
            user_id,
            24.50,
            "Food",
            "Original lunch",
            "2026-10-12",
        )
        close_db()
    return created_id


@pytest.fixture
def other_expense_id(app, other_user_id):
    with app.app_context():
        created_id = create_expense(
            other_user_id,
            41.25,
            "Transport",
            "Other user's expense",
            "2026-10-13",
        )
        close_db()
    return created_id


def _url(app, endpoint, **values):
    with app.test_request_context():
        return url_for(endpoint, **values)


class _SelectedOptionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.selected_values = set()

    def handle_starttag(self, tag, attrs):
        if tag == "option":
            attributes = dict(attrs)
            if "selected" in attributes:
                self.selected_values.add(attributes.get("value"))


class TestEditExpenseQueries:
    def test_get_expense_by_id_for_owner_returns_matching_expense(
        self, app, user_id, expense_id
    ):
        with app.app_context():
            expense = get_expense_by_id(expense_id, user_id)

        assert expense is not None, "Expected the owner's expense to be found"
        assert expense["id"] == expense_id
        assert expense["amount"] == 24.50
        assert expense["category"] == "Food"
        assert expense["description"] == "Original lunch"
        assert expense["date"] == "2026-10-12"

    def test_get_expense_by_id_for_wrong_owner_returns_none(
        self, app, expense_id, other_user_id
    ):
        with app.app_context():
            expense = get_expense_by_id(expense_id, other_user_id)

        assert expense is None, "An expense must not be visible to another user"

    def test_get_expense_by_id_for_missing_id_returns_none(self, app, user_id):
        with app.app_context():
            expense = get_expense_by_id(2_000_000_000, user_id)

        assert expense is None, "A non-existent expense should not be returned"

    def test_update_expense_for_owner_changes_database_row(
        self, app, user_id, expense_id
    ):
        with app.app_context():
            updated_count = update_expense(
                expense_id,
                user_id,
                99.0,
                "Shopping",
                "2026-10-20",
                "Updated purchase",
            )
            updated = get_expense_by_id(expense_id, user_id)

        assert updated_count == 1, "Expected exactly one owned expense to be updated"
        assert updated["amount"] == 99.0
        assert updated["category"] == "Shopping"
        assert updated["date"] == "2026-10-20"
        assert updated["description"] == "Updated purchase"

    def test_update_expense_for_wrong_owner_leaves_row_unchanged(
        self, app, expense_id, user_id
    ):
        with app.app_context():
            updated_count = update_expense(
                expense_id,
                user_id + 100_000,
                99.0,
                "Shopping",
                "2026-10-20",
                "Unauthorized update",
            )
            original = get_expense_by_id(expense_id, user_id)

        assert updated_count == 0, "An update by a non-owner should affect no rows"
        assert original["amount"] == 24.50
        assert original["category"] == "Food"
        assert original["date"] == "2026-10-12"
        assert original["description"] == "Original lunch"


class TestEditExpenseRoutes:
    def test_get_edit_expense_unauthenticated_redirects_to_login(self, client, app):
        response = client.get(_url(app, "edit_expense", id=123))

        assert response.status_code == 302
        assert response.headers["Location"].endswith(_url(app, "login"))

    def test_get_edit_expense_owner_sees_prefilled_form_and_selected_category(
        self, auth_client, app, expense_id
    ):
        response = auth_client.get(_url(app, "edit_expense", id=expense_id))

        assert response.status_code == 200, "Expected the edit form to render"
        assert b'name="amount"' in response.data
        assert b'value="24.5"' in response.data
        assert b'name="date"' in response.data
        assert b'value="2026-10-12"' in response.data
        assert b'name="description"' in response.data
        assert b'value="Original lunch"' in response.data
        parser = _SelectedOptionParser()
        parser.feed(response.get_data(as_text=True))
        assert "Food" in parser.selected_values, "Food should be pre-selected"

    def test_get_edit_expense_for_another_user_returns_404(
        self, auth_client, app, other_expense_id
    ):
        response = auth_client.get(_url(app, "edit_expense", id=other_expense_id))

        assert response.status_code == 404, "Another user's expense must be hidden"

    def test_get_edit_expense_for_missing_id_returns_404(self, auth_client, app):
        response = auth_client.get(_url(app, "edit_expense", id=2_000_000_000))

        assert response.status_code == 404, "A missing expense should return 404"

    def test_post_edit_expense_unauthenticated_redirects_to_login(self, client, app):
        response = client.post(
            _url(app, "edit_expense", id=123),
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-10-20",
                "description": "Unauthenticated attempt",
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith(_url(app, "login"))

    def test_post_edit_expense_valid_data_redirects_and_updates_row(
        self, auth_client, app, user_id, expense_id
    ):
        response = auth_client.post(
            _url(app, "edit_expense", id=expense_id),
            data={
                "amount": "73.25",
                "category": "Health",
                "date": "2026-10-21",
                "description": "Updated checkup",
            },
        )

        assert response.status_code == 302, "A successful edit should redirect"
        assert response.headers["Location"].endswith(_url(app, "profile"))
        with app.app_context():
            updated = get_expense_by_id(expense_id, user_id)
        assert updated["amount"] == 73.25
        assert updated["category"] == "Health"
        assert updated["date"] == "2026-10-21"
        assert updated["description"] == "Updated checkup"

    def test_post_edit_expense_for_another_user_returns_404(
        self, auth_client, app, other_expense_id
    ):
        response = auth_client.post(
            _url(app, "edit_expense", id=other_expense_id),
            data={
                "amount": "73.25",
                "category": "Food",
                "date": "2026-10-21",
                "description": "Unauthorized edit",
            },
        )

        assert response.status_code == 404, "Another user's expense must not update"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("amount", ""),
            ("amount", "0"),
            ("amount", "not-a-number"),
            ("category", "Invalid category"),
            ("date", "not-a-date"),
            ("category", ""),
            ("date", ""),
        ],
    )
    def test_post_edit_expense_invalid_data_rerenders_form_with_error(
        self, auth_client, app, expense_id, field, value
    ):
        form_data = {
            "amount": "18.75",
            "category": "Food",
            "date": "2026-10-22",
            "description": "submitted-description-marker",
        }
        form_data[field] = value

        response = auth_client.post(
            _url(app, "edit_expense", id=expense_id),
            data=form_data,
        )

        assert response.status_code == 200, "Invalid input should re-render the form"
        assert b"submitted-description-marker" in response.data, (
            "The form should retain submitted values after validation fails"
        )
        assert any(
            message in response.data
            for message in (
                b"Amount must be greater than zero",
                b"valid amount",
                b"valid category",
                b"valid date",
            )
        ), "Expected a validation error message in the response"

    def test_post_edit_expense_without_description_saves_null_description(
        self, auth_client, app, user_id, expense_id
    ):
        response = auth_client.post(
            _url(app, "edit_expense", id=expense_id),
            data={
                "amount": "30.00",
                "category": "Bills",
                "date": "2026-10-23",
                "description": "   ",
            },
        )

        assert response.status_code == 302, "A blank optional description is valid"
        with app.app_context():
            updated = get_expense_by_id(expense_id, user_id)
        assert updated["description"] is None, "Blank descriptions should be stored as NULL"

    def test_profile_transaction_row_has_link_to_edit_expense(
        self, auth_client, app, expense_id
    ):
        response = auth_client.get(_url(app, "profile"))

        assert response.status_code == 200
        expected_link = f'href="{_url(app, "edit_expense", id=expense_id)}"'
        assert expected_link.encode() in response.data, (
            "Each transaction should link to its own edit form"
        )
        assert b">Edit</a>" in response.data, "Expected an Edit action in the row"
