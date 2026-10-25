import calendar
import math
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from database.db import (
    create_expense,
    create_user,
    get_user_by_email,
    init_app,
    init_db,
    seed_db,
)
from database.queries import (
    get_category_breakdown,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    update_expense,
)

app = Flask(__name__)
app.config["DATABASE"] = os.path.join(app.root_path, "spendly.db")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Initialize database
init_app(app)

with app.app_context():
    init_db()
    seed_db()


@app.context_processor
def inject_navigation_user():
    """Provide a display name for the authenticated navigation."""
    if session.get("user_id"):
        user = get_user_by_id(session["user_id"])
        return {"nav_username": user["name"] if user else None}
    return {"nav_username": None}


# ------------------------------------------------------------------ #
# Routes                                                             #
# ------------------------------------------------------------------ #

def _subtract_months(value, months):
    month_index = value.year * 12 + value.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _category_css_class(category_name):
    return re.sub(r"[^a-z0-9]+", "-", category_name.lower()).strip("-")


def _profile_date_filter():
    preset = request.args.get("preset", "").strip()
    valid_presets = {
        "all_time",
        "this_month",
        "last_3_months",
        "last_6_months",
        "custom",
    }
    if preset and preset not in valid_presets:
        abort(400, description="Select a valid date filter.")

    if preset in {"this_month", "last_3_months", "last_6_months"}:
        today = date.today()
        if preset == "this_month":
            start_date = today.replace(day=1)
            period_label = "This Month"
        elif preset == "last_3_months":
            start_date = _subtract_months(today, 3)
            period_label = "Last 3 Months"
        else:
            start_date = _subtract_months(today, 6)
            period_label = "Last 6 Months"
        return start_date.isoformat(), today.isoformat(), preset, period_label

    if preset == "all_time":
        return None, None, "all_time", "All Time"

    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None
    for label, date_value in (("Start date", start_date), ("End date", end_date)):
        if date_value is not None:
            try:
                parsed_date = date.fromisoformat(date_value)
            except ValueError:
                abort(400, description=f"{label} must be a valid YYYY-MM-DD date.")
            if parsed_date.isoformat() != date_value:
                abort(400, description=f"{label} must be a valid YYYY-MM-DD date.")

    if start_date and end_date and start_date > end_date:
        abort(400, description="Start date must be on or before end date.")

    if start_date and end_date:
        period_label = f"{start_date} to {end_date}"
    elif start_date:
        period_label = f"From {start_date}"
    elif end_date:
        period_label = f"Through {end_date}"
    else:
        period_label = "All Time"

    selected_preset = "custom" if start_date or end_date else "all_time"
    return start_date, end_date, selected_preset, period_label


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Handle user registration.

    GET: Render registration form
    POST: Process form submission, create user account
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not all([name, email, password, confirm_password]):
            flash("All fields are required.", "error")
            return render_template("register.html"), 400

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html"), 400

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html"), 400

        user_id = create_user(name, email, password)
        if user_id is None:
            flash("Email already registered.", "error")
            return render_template("register.html"), 400

        flash("Account created. Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if user is not None and check_password_hash(
            user["password_hash"], password
        ):
            session["user_id"] = user["id"]
            return redirect(url_for("profile"))

        flash("Invalid email or password.", "error")
        return render_template("login.html"), 401

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                 #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    start_date, end_date, selected_preset, period_label = (
        _profile_date_filter()
    )

    user_id = session["user_id"]
    profile_user = get_user_by_id(user_id)
    if profile_user is None:
        abort(404)
    profile_user["initials"] = "".join(
        part[0] for part in profile_user["name"].split()[:2]
    ).upper()

    stats = get_summary_stats(user_id, start_date, end_date)
    summary_stats = [
        {
            "label": "Total spent",
            "value": f"₹{stats['total_spent']:,.2f}",
            "detail": period_label,
        },
        {
            "label": "Transactions",
            "value": str(stats["transaction_count"]),
            "detail": period_label,
        },
        {
            "label": "Top category",
            "value": stats["top_category"],
            "detail": "Highest spending category",
        },
    ]

    transactions = [
        {
            **transaction,
            "class": _category_css_class(transaction["category"]),
        }
        for transaction in get_recent_transactions(
            user_id, start_date=start_date, end_date=end_date
        )
    ]

    categories = [
        {
            "name": category["name"],
            "amount": f"₹{category['amount']:,.2f}",
            "value": int(category["pct"]),
            "class": _category_css_class(category["name"]),
        }
        for category in get_category_breakdown(user_id, start_date, end_date)
    ]

    return render_template(
        "profile.html",
        profile_user=profile_user,
        summary_stats=summary_stats,
        transactions=transactions,
        categories=categories,
        category_max=100,
        selected_start_date=start_date or "",
        selected_end_date=end_date or "",
        selected_preset=selected_preset,
        period_label=period_label,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    categories = [
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    ]
    form_data = {
        "amount": request.form.get("amount", "").strip(),
        "category": request.form.get("category", ""),
        "date": request.form.get("date", date.today().isoformat()),
        "description": request.form.get("description", "").strip(),
    }

    if request.method == "POST":
        error = None
        try:
            amount = Decimal(form_data["amount"])
            if not amount.is_finite() or amount <= 0:
                error = "Amount must be greater than zero."
            else:
                amount_value = float(amount)
                if not math.isfinite(amount_value) or amount_value <= 0:
                    error = "Enter a valid amount greater than zero."
        except InvalidOperation:
            error = "Enter a valid amount greater than zero."

        try:
            expense_date = date.fromisoformat(form_data["date"])
            if expense_date.isoformat() != form_data["date"]:
                raise ValueError
        except ValueError:
            error = "Enter a valid date."

        if form_data["category"] not in categories:
            error = "Select a valid category."

        if error:
            flash(error, "error")
            return render_template(
                "add_expense.html",
                categories=categories,
                form_data=form_data,
            ), 400

        create_expense(
            session["user_id"],
            amount_value,
            form_data["category"],
            form_data["description"] or None,
            expense_date.isoformat(),
        )
        flash("Expense added successfully.", "success")
        return redirect(url_for("profile"))

    return render_template(
        "add_expense.html",
        categories=categories,
        form_data=form_data,
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    categories = [
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    ]

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "POST":
        form_data = {
            "amount": request.form.get("amount", "").strip(),
            "category": request.form.get("category", ""),
            "date": request.form.get("date", "").strip(),
            "description": request.form.get("description", "").strip(),
        }

        error = None
        try:
            amount = Decimal(form_data["amount"])
            if not amount.is_finite() or amount <= 0:
                error = "Amount must be greater than zero."
            else:
                amount_value = float(amount)
                if not math.isfinite(amount_value) or amount_value <= 0:
                    error = "Enter a valid amount greater than zero."
        except InvalidOperation:
            error = "Enter a valid amount greater than zero."

        try:
            expense_date = date.fromisoformat(form_data["date"])
            if expense_date.isoformat() != form_data["date"]:
                raise ValueError
        except ValueError:
            error = "Enter a valid date."

        if form_data["category"] not in categories:
            error = "Select a valid category."

        if error:
            flash(error, "error")
            return render_template(
                "edit_expense.html",
                expense={
                    "id": id,
                    "amount": form_data["amount"],
                    "category": form_data["category"],
                    "date": form_data["date"],
                    "description": form_data["description"],
                },
                categories=categories,
                form_data=form_data,
            ), 400

        normalized_description = form_data["description"] or None
        update_expense(
            id,
            session["user_id"],
            float(amount_value),
            form_data["category"],
            expense_date.isoformat(),
            normalized_description,
        )
        flash("Expense updated successfully.", "success")
        return redirect(url_for("profile"))

    expense_dict = {
        "id": expense["id"],
        "amount": expense["amount"],
        "category": expense["category"],
        "date": expense["date"],
        "description": expense["description"] or "",
    }
    return render_template(
        "edit_expense.html",
        expense=expense_dict,
        categories=categories,
        form_data=expense_dict,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
