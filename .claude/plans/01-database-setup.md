# Implementation Plan: Database Setup

## Context

This step implements the database layer for the Spendly expense tracker. The spec (`database/db.py` stub and `app.py` without DB init) required building the foundational data layer that all future features depend on.

**Status: Implementation is complete.** Both files have been updated and diagnostics are clean.

---

## What Was Done

### `database/db.py` — fully implemented

- `get_db()`: Opens `spendly.db` in project root, sets `row_factory = sqlite3.Row`, enables `PRAGMA foreign_keys = ON`, stores connection in Flask `g`
- `close_db()`: Teardown handler that pops and closes the connection from `g`
- `init_db()`: Creates `users` and `expenses` tables with `CREATE TABLE IF NOT EXISTS` — safe to call multiple times
- `seed_db()`: Checks if users table has data first; if empty, inserts demo user (hashed with `werkzeug.security.generate_password_hash`) and 8 sample expenses across all 7 categories
- `init_app(app)`: Registers `close_db` with `app.teardown_appcontext`

### `app.py` — updated

- Added `import os`
- Imported `init_app`, `init_db`, `seed_db` from `database.db`
- Set `app.config["DATABASE"]`
- Called `init_app(app)` to register teardown
- Called `init_db()` and `seed_db()` inside `with app.app_context()` on startup

---

## Schema

**users**: `id`, `name` (NOT NULL), `email` (UNIQUE NOT NULL), `password_hash` (NOT NULL), `created_at`

**expenses**: `id`, `user_id` (FK → users.id ON DELETE CASCADE), `amount` (REAL), `category`, `description`, `date` (TEXT, YYYY-MM-DD), `created_at`

---

## Remaining Verification

Run the following to confirm everything works end-to-end:

```bash
python app.py           # app should start on port 5001, spendly.db created
pytest                  # all existing tests should pass
```

Then inspect the database:

```bash
python -c "import sqlite3; db = sqlite3.connect('spendly.db'); db.row_factory = sqlite3.Row; print([dict(r) for r in db.execute('SELECT * FROM users')]); print(db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0])"
```

Expected: 1 user (Demo User / demo@spendly.com) and 8 expenses.