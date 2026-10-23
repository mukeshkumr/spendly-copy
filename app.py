import os

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_user_by_email, init_app, init_db, seed_db

app = Flask(__name__)
app.config["DATABASE"] = os.path.join(app.root_path, "spendly.db")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

PROFILE_USER = {
    "name": "Aarav Sharma",
    "email": "aarav.sharma@example.com",
    "initials": "AS",
    "member_since": "October 2025",
}

# Initialize database
init_app(app)

with app.app_context():
    init_db()
    seed_db()


@app.context_processor
def inject_navigation_user():
    """Provide a display name for the authenticated navigation."""
    if session.get("user_id"):
        return {"nav_username": PROFILE_USER["name"]}
    return {"nav_username": None}


# ------------------------------------------------------------------ #
# Routes                                                             #
# ------------------------------------------------------------------ #

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
            return redirect(url_for("landing"))

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

    summary_stats = [
        {"label": "Spent this month", "value": "₹19,420", "detail": "October 2026"},
        {"label": "Transactions", "value": "42", "detail": "This month"},
        {"label": "Top category", "value": "Food", "detail": "₹8,450 this month"},
    ]

    transactions = [
        {
            "date": "Oct 22, 2026",
            "description": "Weekly groceries",
            "category": "Food",
            "amount": "₹1,240",
        },
        {
            "date": "Oct 21, 2026",
            "description": "Electricity bill",
            "category": "Bills",
            "amount": "₹2,180",
        },
        {
            "date": "Oct 20, 2026",
            "description": "Metro card recharge",
            "category": "Transport",
            "amount": "₹500",
        },
        {
            "date": "Oct 18, 2026",
            "description": "Dinner with friends",
            "category": "Food",
            "amount": "₹860",
        },
        {
            "date": "Oct 16, 2026",
            "description": "Pharmacy",
            "category": "Health",
            "amount": "₹640",
        },
    ]

    categories = [
        {"name": "Food", "amount": "₹8,450", "value": 8450, "class": "food"},
        {"name": "Bills", "amount": "₹4,220", "value": 4220, "class": "bills"},
        {"name": "Shopping", "amount": "₹3,460", "value": 3460, "class": "shopping"},
        {"name": "Transport", "amount": "₹1,240", "value": 1240, "class": "transport"},
        {"name": "Health", "amount": "₹1,100", "value": 1100, "class": "health"},
        {
            "name": "Entertainment",
            "amount": "₹950",
            "value": 950,
            "class": "entertainment",
        },
    ]

    return render_template(
        "profile.html",
        profile_user=PROFILE_USER,
        summary_stats=summary_stats,
        transactions=transactions,
        categories=categories,
        category_max=8450,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
