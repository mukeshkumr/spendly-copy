# Spec: Delete Expense

## Overview
Implement the Step 9 expense-deletion flow so a logged-in user can permanently remove one of their own expenses. The existing delete route is a placeholder; this feature replaces it with a confirmation page on GET and a deletion on POST, so visiting a link cannot delete data by itself. Removing an expense must immediately remove it from the user's profile totals and transaction history.

## Depends on
- Steps 01–08 — database setup, authentication, profile queries, and expense creation/editing must be complete.

## Routes
- `GET /expenses/<int:id>/delete` — show a confirmation page for the current user's expense — logged-in
- `POST /expenses/<int:id>/delete` — delete the current user's expense and redirect to the profile — logged-in

## Database changes
No database changes. The existing `expenses` table contains the required `id` and `user_id` columns. Add a parameterised query helper in `database/queries.py` to delete only a row matching both the expense ID and authenticated user ID.

## Templates
- **Create:** `templates/delete_expense.html` — show the expense details and ask the user to confirm; submit a POST form to the delete route and provide a cancel link to the profile.
- **Modify:** `templates/profile.html` — add a Delete action for each transaction alongside the existing Edit action.

## Files to change
- `app.py` — replace the GET-only placeholder with authenticated GET and POST handling, ownership/not-found responses, and success feedback.
- `database/queries.py` — add a delete helper scoped by both expense ID and user ID.
- `templates/profile.html` — add per-transaction delete links or forms using `url_for()`.
- `static/css/profile.css` — style the new delete action using existing CSS variables.

## Files to create
- `templates/delete_expense.html`
- `tests/test_delete_expense.py`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Require authentication for GET and POST; unauthenticated requests redirect to login.
- GET must only display a confirmation page; only POST may delete an expense.
- Scope both expense lookup and deletion to `id = ? AND user_id = ?`; return 404 for missing expenses and expenses owned by another user.
- Do not accept a user ID from form input. Use the authenticated user's ID from the session.
- On successful deletion, flash a success message and redirect to `url_for("profile")`.
- Use `url_for()` for every internal link and form action; do not hardcode URLs.
- Keep all SQL in `database/queries.py`, not in route functions.

## Definition of done
- [ ] An unauthenticated GET or POST to `/expenses/<id>/delete` redirects to the login page and does not delete any expense.
- [ ] An authenticated GET for the user's expense renders a confirmation page with its details and a POST confirmation form.
- [ ] An authenticated GET or POST for a nonexistent expense or another user's expense returns 404.
- [ ] GET does not delete an expense; cancelling confirmation returns to the profile with the expense intact.
- [ ] Confirming deletion with POST removes only the selected user's expense, flashes success feedback, and redirects to the profile.
- [ ] After deletion, the expense no longer appears in the profile transactions and profile totals reflect its removal.
- [ ] The profile provides a working Delete action for each transaction, and submitting it uses POST.
- [ ] The database delete helper uses parameterised SQL scoped to both expense ID and user ID.
