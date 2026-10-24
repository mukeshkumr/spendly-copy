# Spec: Add Expense

## Overview
Implement the Step 7 expense-entry flow so authenticated users can record an expense with an amount, one of Spendly's fixed categories, a date, and an optional description. This turns the existing `/expenses/add` placeholder into a working form and persists entries in the existing expenses table, allowing the profile page's live spending summaries to reflect them.

## Depends on
- Steps 01–06 — database setup, registration, login/logout, profile page, profile database queries, and date filtering must be complete.

## Routes
- `GET /expenses/add` — render the expense form — logged-in
- `POST /expenses/add` — validate and save the current user's expense, then redirect to the profile page — logged-in

## Database changes
No database changes. The existing `expenses` table has the required `user_id`, `amount`, `category`, `description`, and `date` columns. Add a parameterised database helper to insert a new expense.

## Templates
- **Create:** `templates/add_expense.html` — expense form with amount, category, date, optional description, and validation feedback.
- **Modify:** `templates/profile.html` — add a link to the add-expense form so a logged-in user can reach the flow from their profile.

## Files to change
- `app.py` — implement the authenticated GET/POST `/expenses/add` route, server-side validation, and redirect/flash behavior.
- `database/db.py` — add a parameterised helper to insert an expense for a user.
- `templates/profile.html` — add the add-expense entry point.
- `static/css/profile.css` — style the new profile entry point using existing CSS variables.

## Files to create
- `templates/add_expense.html`
- `static/css/add_expense.css`
- `tests/test_add_expense.py`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Keep database queries and writes in `database/db.py`, not in route functions.
- Require `session["user_id"]` for both methods; redirect unauthenticated requests to the login page.
- Allow only the fixed categories: Food, Transport, Bills, Health, Entertainment, Shopping, and Other.
- Require a valid positive amount and a valid `YYYY-MM-DD` date; description is optional. Reject invalid form data with a clear message and do not insert an expense.
- Set `user_id` from the authenticated session; never accept it from form input.
- On successful submission, save the expense and redirect to the profile page with a success message.
- Use `url_for()` for every internal link and form action.

## Definition of done
- [ ] Visiting `/expenses/add` while logged in renders a form containing amount, category, date, and optional description fields.
- [ ] Submitting valid form data inserts one expense with the current user's ID and redirects to the profile page.
- [ ] The saved expense appears in the profile transaction list and is reflected in its spending totals.
- [ ] An unauthenticated GET or POST to `/expenses/add` redirects to the login page and creates no expense.
- [ ] Missing or non-positive amounts, invalid dates, and categories outside the fixed list show a clear validation error and create no expense.
- [ ] Omitting the optional description successfully saves the expense.
