# Spec: Date Filter for Profile Page

## Overview
Add an optional date-range filter to the logged-in profile page so users can review spending for a chosen period instead of only seeing all-time totals. Users can enter inclusive start and end dates, apply the range through the existing profile route, and clear the range to return to all-time data. The selected range must affect summary statistics, recent transactions, and category breakdown consistently.

## Depends on
- Steps 01–05 — database setup, registration, authentication, profile page, and profile database queries must be complete.

## Routes
- `GET /profile` — accept optional start and end date query parameters and render date-filtered profile data — logged-in (existing route, modified)

## Database changes
No database changes. The existing `expenses.date` column stores dates as `YYYY-MM-DD` text and can be filtered directly.

## Templates
- **Create:** None
- **Modify:** `templates/profile.html` — add an accessible GET form with start-date and end-date inputs, an apply control, and a clear-filter link; reflect the selected dates and period in the rendered profile.

## Files to change
- `app.py` — parse and validate optional date query parameters, pass the selected range to the profile query helpers, and provide filter context to the template.
- `database/queries.py` — add optional inclusive date bounds to the profile summary, recent transaction, and category breakdown queries, preserving current all-time behavior when no bounds are supplied.
- `templates/profile.html` — add the date filter and display the selected period consistently.
- `static/css/profile.css` — style the date filter using existing CSS variables and responsive layout conventions.

## Files to create
- `tests/test_date_filter.py` — cover date validation, filtered profile results, bounds, and unfiltered behavior.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Keep the existing `GET /profile` route and login guard; do not add a new route.
- Treat provided dates as optional inclusive `YYYY-MM-DD` bounds; with neither bound supplied, preserve the current all-time profile behavior.
- Reject malformed dates and a start date later than the end date with a clear validation response; do not silently ignore invalid filters.
- Apply the same selected bounds to summary statistics, the newest-first recent transaction list, and category totals/percentages.
- Keep all SQL in `database/queries.py` and use bound SQL parameters for date values.
- Keep the filter form usable without JavaScript and use `url_for()` for internal links.

## Definition of done
- [ ] Opening `/profile` while logged in without date parameters still shows the existing all-time summary, transactions, and category breakdown.
- [ ] Submitting a valid start date and end date filters summary totals, transaction count, recent transactions, and category breakdown to expenses on or between those dates, inclusive.
- [ ] Supplying only a start date or only an end date applies that inclusive bound to all profile data sections.
- [ ] The selected date values remain visible in the form after filtering, and clearing the filter restores all-time results.
- [ ] A malformed date or a start date later than the end date produces a clear client error and does not silently show unfiltered data.
- [ ] An unauthenticated request to `/profile` continues to redirect to `/login`, including when date parameters are supplied.
- [ ] Existing query-helper behavior remains unchanged when no date bounds are passed.
