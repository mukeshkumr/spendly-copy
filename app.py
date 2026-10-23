import os

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

from database.db import create_user, get_user_by_email, init_app, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
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

    user_id = session["user_id"]
    profile_user = get_user_by_id(user_id)
    if profile_user is None:
        abort(404)
    profile_user["initials"] = "".join(
        part[0] for part in profile_user["name"].split()[:2]
    ).upper()

    stats = get_summary_stats(session["user_id"])
    summary_stats = [
        {
            "label": "Total spent",
            "value": f"₹{stats['total_spent']:,.2f}",
            "detail": "All time",
        },
        {
            "label": "Transactions",
            "value": str(stats["transaction_count"]),
            "detail": "All time",
        },
        {
            "label": "Top category",
            "value": stats["top_category"],
            "detail": "Highest spending category",
        },
    ]

    transactions = get_recent_transactions(user_id)

    categories = [
        {
            "name": category["name"],
            "amount": f"₹{category['amount']:,.2f}",
            "value": int(category["pct"]),
            "class": category["name"].lower(),
        }
        for category in get_category_breakdown(user_id)
    ]

    return render_template(
        "profile.html",
        profile_user=profile_user,
        summary_stats=summary_stats,
        transactions=transactions,
        categories=categories,
        category_max=100,
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
