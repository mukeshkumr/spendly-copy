# Implementation Plan: User Registration (Step 02)

## Context

The `/register` route exists as a GET-only stub that renders a form with no backend processing. This step turns it into a fully functional registration flow: validating input, hashing passwords, inserting a new user, and redirecting to the login page. It's the prerequisite for all authentication-gated features in subsequent steps.

No new packages are needed — `werkzeug.security` is already imported in `database/db.py` and used in `seed_db()`.

---

## Files to Change

| File | What changes |
|---|---|
| `database/db.py` | Add `create_user()` helper |
| `app.py` | Add `secret_key`, expand imports, upgrade `register()` to handle POST |
| `templates/register.html` | Fix form action, add `confirm_password` field, swap error block for flash |
| `static/css/style.css` | Add `.auth-success` style to match existing `.auth-error` |

## Files to Create

| File | What it is |
|---|---|
| `tests/__init__.py` | Empty file to make `tests/` a package |
| `tests/test_registration.py` | Pytest tests for the registration feature |

---

## Step-by-step Changes

### 1. `database/db.py` — Add `create_user()`

Add after `init_app()` (after line 140):

```python
def create_user(name: str, email: str, password: str) -> int | None:
    """Hash password and insert a new user row.

    Returns the new user's id, or None if the email is already taken.
    """
    db = get_db()
    existing = db.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()
    if existing:
        return None
    password_hash = generate_password_hash(password)
    cursor = db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, password_hash),
    )
    db.commit()
    return cursor.lastrowid
```

Key notes:
- `generate_password_hash` is already imported on line 6 — no new import needed
- Returns `None` instead of raising so the route can flash a user-facing message
- Parameterized query (`?`) — no f-strings in SQL

---

### 2. `app.py` — secret_key, imports, route

**Add `secret_key` after line 8** (`app.config["DATABASE"] = ...`):
```python
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
```

**Replace the Flask import on line 3**:
```python
from flask import Flask, flash, redirect, render_template, request, url_for
```

**Add `create_user` import** alongside the existing db import:
```python
from database.db import create_user, init_app, init_db, seed_db
```

**Replace the stub `register()` route (lines 37–39)**:
```python
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([name, email, password, confirm_password]):
            flash("All fields are required.")
            return render_template("register.html"), 400

        if password != confirm_password:
            flash("Passwords do not match.")
            return render_template("register.html"), 400

        if len(password) < 8:
            flash("Password must be at least 8 characters.")
            return render_template("register.html"), 400

        user_id = create_user(name, email, password)
        if user_id is None:
            flash("Email already registered.")
            return render_template("register.html"), 400

        flash("Account created. Please sign in.")
        return redirect(url_for("login"))

    return render_template("register.html")
```

Validation order: empty fields → password match → password length → email uniqueness. Each failure re-renders the form with a flash message; no redirect on error.

---

### 3. `templates/register.html` — three targeted edits

**a. Fix form action (line 20):**
```html
<!-- before -->
<form method="POST" action="/register">

<!-- after -->
<form method="POST" action="{{ url_for('register') }}">
```

**b. Replace `{% if error %}` block (lines 16–18) with flash display:**
```html
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        {% for category, message in messages %}
        <div class="auth-{{ category }}">{{ message }}</div>
        {% endfor %}
    {% endif %}
{% endwith %}
```

**c. Add `confirm_password` field after the password `<div>` (after line 38), before the submit button:**
```html
<div class="form-group">
    <label for="confirm_password">Confirm password</label>
    <input type="password" id="confirm_password" name="confirm_password"
           class="form-input" placeholder="Re-enter your password"
           required>
</div>
```

---

### 4. `static/css/style.css` — Add `.auth-success`

After the existing `.auth-error` block, add:
```css
.auth-success {
    background: var(--accent-light);
    color: var(--accent);
    border: 1px solid #c8e6c9;
    border-radius: var(--radius-sm);
    padding: 0.75rem 1rem;
    font-size: 0.875rem;
    margin-bottom: 1.25rem;
}
```
This uses existing CSS variables and matches the style of `.auth-error`.

---

### 5. Tests — `tests/__init__.py` + `tests/test_registration.py`

`tests/__init__.py`: empty file.

`tests/test_registration.py` — covers all definition-of-done items:

```python
"""Tests for user registration (Step 02)."""
import pytest
from app import app as flask_app
from database.db import get_db, init_db


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    flask_app.config["DATABASE"] = ":memory:"
    with flask_app.app_context():
        init_db()
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_get_register_renders(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"Create your account" in response.data


def test_valid_registration_redirects_to_login(client):
    response = client.post("/register", data={
        "name": "Test User", "email": "test@example.com",
        "password": "password123", "confirm_password": "password123",
    })
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_valid_registration_creates_user(client, app):
    client.post("/register", data={
        "name": "New User", "email": "new@example.com",
        "password": "password123", "confirm_password": "password123",
    })
    with app.app_context():
        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?", ("new@example.com",)
        ).fetchone()
    assert user is not None
    assert user["name"] == "New User"


def test_password_is_stored_hashed(client, app):
    client.post("/register", data={
        "name": "Hash User", "email": "hash@example.com",
        "password": "plaintext1", "confirm_password": "plaintext1",
    })
    with app.app_context():
        user = get_db().execute(
            "SELECT password_hash FROM users WHERE email = ?", ("hash@example.com",)
        ).fetchone()
    assert user["password_hash"] != "plaintext1"
    assert user["password_hash"].startswith("scrypt:")


def test_mismatched_passwords_shows_error(client):
    response = client.post("/register", data={
        "name": "User", "email": "user@example.com",
        "password": "password123", "confirm_password": "different",
    })
    assert response.status_code == 400
    assert b"Passwords do not match" in response.data


def test_duplicate_email_shows_error(client):
    data = {"name": "A", "email": "dup@example.com",
            "password": "password123", "confirm_password": "password123"}
    client.post("/register", data=data)
    response = client.post("/register", data=data)
    assert response.status_code == 400
    assert b"already registered" in response.data.lower()


def test_empty_fields_shows_error(client):
    response = client.post("/register", data={
        "name": "", "email": "a@b.com",
        "password": "password123", "confirm_password": "password123",
    })
    assert response.status_code == 400
    assert b"required" in response.data


def test_short_password_shows_error(client):
    response = client.post("/register", data={
        "name": "User", "email": "user@example.com",
        "password": "abc", "confirm_password": "abc",
    })
    assert response.status_code == 400
    assert b"8 characters" in response.data
```

---

## Verification

```bash
# Run the app and manually test the form
python app.py
# Visit http://localhost:5001/register

# Run tests (use pytest, NOT python directly)
pytest tests/test_registration.py -v

# Spot-check the DB — password_hash should start with scrypt:
sqlite3 spendly.db "SELECT email, password_hash FROM users LIMIT 3"
```

Definition-of-done checklist (from spec):
- [x] `GET /register` renders without errors
- [x] Valid submission creates user and redirects to `/login`
- [x] Mismatched passwords → error, no DB insert
- [x] Duplicate email → "Email already registered"
- [x] Empty field → validation error
- [x] Password stored hashed, never plaintext
- [x] No duplicate user on repeated same-email submissions