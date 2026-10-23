import importlib
import re
import secrets
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import g
from werkzeug.security import generate_password_hash


@pytest.fixture
def profile_app(tmp_path_factory):
    import database.db as database

    database_path = tmp_path_factory.mktemp("profile-test-db") / "spendly.db"

    def get_test_db():
        if "db" not in g:
            g.db = sqlite3.connect(database_path)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    with patch.object(database, "get_db", get_test_db):
        application = importlib.import_module("app").app

    return application


@pytest.fixture
def client(profile_app):
    original_testing = profile_app.config["TESTING"]
    profile_app.config["TESTING"] = True
    yield profile_app.test_client()
    profile_app.config["TESTING"] = original_testing


def test_profile_redirects_guests_to_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_successful_login_redirects_to_profile(client, monkeypatch):
    password = secrets.token_urlsafe(24)
    user = {
        "id": 101,
        "password_hash": generate_password_hash(password),
    }
    app_module = importlib.import_module("app")
    monkeypatch.setattr(app_module, "get_user_by_email", lambda _email: user)

    response = client.post(
        "/login",
        data={"email": "profile-test@example.com", "password": password},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")


def test_profile_renders_hardcoded_content_without_database_access(client):
    with client.session_transaction() as user_session:
        user_session["user_id"] = 101

    with patch(
        "database.db.get_db",
        side_effect=AssertionError("Profile page must not access the database"),
    ):
        response = client.get("/profile")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Aarav Sharma" in html
    assert "aarav.sharma@example.com" in html
    assert "₹19,420" in html
    assert html.count('class="profile-stat-card"') == 3
    assert html.count('class="transaction-description"') == 5
    assert html.count('class="category-list-item"') == 6
    assert "Spending by category" in html
    assert "password_hash" not in html


def test_navigation_shows_authenticated_or_guest_links(client):
    with client.session_transaction() as user_session:
        user_session["user_id"] = 101
    authenticated_response = client.get("/")
    authenticated_html = authenticated_response.get_data(as_text=True)

    assert authenticated_response.status_code == 200
    assert "Aarav Sharma" in authenticated_html
    assert "Sign out" in authenticated_html
    assert "Get started" not in authenticated_html

    with client.session_transaction() as user_session:
        user_session.clear()
    guest_response = client.get("/")
    guest_html = guest_response.get_data(as_text=True)

    assert guest_response.status_code == 200
    assert "Sign in" in guest_html
    assert "Get started" in guest_html
    assert "Sign out" not in guest_html


def test_profile_template_uses_no_inline_styles_or_hex_colors():
    template_path = Path(__file__).resolve().parents[1] / "templates" / "profile.html"
    template = template_path.read_text(encoding="utf-8")

    assert not re.search(r'#[0-9a-fA-F]{3,8}\b', template)
    assert not re.search(r"\sstyle\s*=", template, re.IGNORECASE)
