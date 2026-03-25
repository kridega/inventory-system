"""
Inventory Management System (Flask + SQLite)

Core ideas:
- users table: authentication + roles (Admin/User)
- parts table: stores total_quantity only (NOT current stock)
- transactions table: stores issue/return events
- Stock is calculated dynamically:
    stock = total_quantity - issued + returned
"""

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash
)
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # IMPORTANT: change in real deployments

DB_NAME = "database.db"

LOW_STOCK_THRESHOLD = 5  # You can change this value as needed


# -----------------------------
# Database Helpers
# -----------------------------
def get_db_connection():
    """Create a SQLite connection with Row factory for dict-like access."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create required tables if they do not exist, and seed a default admin."""
    conn = get_db_connection()
    cur = conn.cursor()

    # users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'User'))
        )
    """)

    # parts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            total_quantity INTEGER NOT NULL CHECK(total_quantity >= 0)
        )
    """)

    # transactions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL,
            user TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('issue', 'return')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            timestamp TEXT NOT NULL,
            FOREIGN KEY(part_id) REFERENCES parts(id)
        )
    """)

    # Seed default admin if none exists
    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    cnt = cur.fetchone()["cnt"]
    if cnt == 0:
        default_admin_user = "admin"
        default_admin_pass = "admin123"  # shown in README; user should change
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (default_admin_user, generate_password_hash(default_admin_pass), "Admin")
        )

    conn.commit()
    conn.close()


# -----------------------------
# Auth Decorators
# -----------------------------
def login_required(view_func):
    """Redirect to login page if not authenticated."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper


def admin_required(view_func):
    """Allow only Admin role."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "Admin":
            flash("Access denied: Admins only.", "danger")
            return redirect(url_for("dashboard"))
        return view_func(*args, **kwargs)
    return wrapper


# -----------------------------
# Inventory / Stock Computation
# -----------------------------
def get_part_stock(part_id: int) -> int:
    """
    Dynamic stock:
      stock = total_quantity - issued + returned
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT total_quantity FROM parts WHERE id = ?", (part_id,))
    part = cur.fetchone()
    if not part:
        conn.close()
        return 0

    total_quantity = part["total_quantity"]

    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN type='issue' THEN quantity ELSE 0 END), 0) AS issued,
            COALESCE(SUM(CASE WHEN type='return' THEN quantity ELSE 0 END), 0) AS returned
        FROM transactions
        WHERE part_id = ?
    """, (part_id,))
    row = cur.fetchone()
    conn.close()

    issued = row["issued"]
    returned = row["returned"]
    stock = total_quantity - issued + returned
    return stock


def get_parts_with_stock(search: str = ""):
    """Return parts list with computed stock and issued/returned totals for display."""
    conn = get_db_connection()
    cur = conn.cursor()

    if search:
        cur.execute("SELECT * FROM parts WHERE name LIKE ? ORDER BY name", (f"%{search}%",))
    else:
        cur.execute("SELECT * FROM parts ORDER BY name")

    parts = cur.fetchall()
    conn.close()

    result = []
    for p in parts:
        stock = get_part_stock(p["id"])
        result.append({
            "id": p["id"],
            "name": p["name"],
            "total_quantity": p["total_quantity"],
            "stock": stock
        })
    return result


def get_recent_transactions(limit: int = 10):
    """Get recent transactions joined with part name."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.*, p.name AS part_name
        FROM transactions t
        JOIN parts p ON p.id = t.part_id
        ORDER BY t.id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


# -----------------------------
# Routes: Auth
# -----------------------------
@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()

        if not user or not check_password_hash(user["password"], password):
            flash("Invalid username or password.", "danger")
            return render_template("login.html")

        session["username"] = user["username"]
        session["role"] = user["role"]
        flash(f"Welcome, {user['username']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# -----------------------------
# Routes: Dashboard
# -----------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    parts = get_parts_with_stock()
    total_parts = len(parts)

    # Low stock items
    low_stock = [p for p in parts if p["stock"] <= LOW_STOCK_THRESHOLD]

    recent_transactions = get_recent_transactions(limit=8)

    return render_template(
        "dashboard.html",
        total_parts=total_parts,
        low_stock=low_stock,
        low_stock_threshold=LOW_STOCK_THRESHOLD,
        recent_transactions=recent_transactions
    )


# -----------------------------
# Routes: Parts Management
# -----------------------------
@app.route("/parts")
@login_required
def parts():
    q = request.args.get("q", "").strip()
    parts_list = get_parts_with_stock(search=q)
    return render_template("parts.html", parts=parts_list, q=q)


@app.route("/parts/add", methods=["POST"])
@admin_required
def add_part():
    name = request.form.get("name", "").strip()
    total_quantity = request.form.get("total_quantity", "").strip()

    if not name:
        flash("Part name is required.", "danger")
        return redirect(url_for("parts"))

    try:
        total_quantity_int = int(total_quantity)
        if total_quantity_int < 0:
            raise ValueError
    except ValueError:
        flash("Total quantity must be a non-negative integer.", "danger")
        return redirect(url_for("parts"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO parts (name, total_quantity) VALUES (?, ?)",
            (name, total_quantity_int)
        )
        conn.commit()
        flash("Part added successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Part name already exists.", "danger")
    finally:
        conn.close()

    return redirect(url_for("parts"))


@app.route("/parts/edit/<int:part_id>", methods=["POST"])
@admin_required
def edit_part(part_id):
    name = request.form.get("name", "").strip()
    total_quantity = request.form.get("total_quantity", "").strip()

    if not name:
        flash("Part name is required.", "danger")
        return redirect(url_for("parts"))

    try:
        total_quantity_int = int(total_quantity)
        if total_quantity_int < 0:
            raise ValueError
    except ValueError:
        flash("Total quantity must be a non-negative integer.", "danger")
        return redirect(url_for("parts"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE parts SET name = ?, total_quantity = ? WHERE id = ?",
            (name, total_quantity_int, part_id)
        )
        if cur.rowcount == 0:
            flash("Part not found.", "danger")
        else:
            flash("Part updated successfully.", "success")
        conn.commit()
    except sqlite3.IntegrityError:
        flash("Part name already exists.", "danger")
    finally:
        conn.close()

    return redirect(url_for("parts"))


@app.route("/parts/delete/<int:part_id>", methods=["POST"])
@admin_required
def delete_part(part_id):
    # Optional: block deletion if there are transactions
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS cnt FROM transactions WHERE part_id = ?", (part_id,))
    cnt = cur.fetchone()["cnt"]
    if cnt > 0:
        conn.close()
        flash("Cannot delete a part that has transaction history.", "danger")
        return redirect(url_for("parts"))

    cur.execute("DELETE FROM parts WHERE id = ?", (part_id,))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        flash("Part not found.", "danger")
    else:
        flash("Part deleted successfully.", "success")

    return redirect(url_for("parts"))


# -----------------------------
# Routes: Transactions
# -----------------------------
@app.route("/transactions")
@login_required
def transactions():
    # Filters
    t_type = request.args.get("type", "").strip()   # issue/return/empty
    part_q = request.args.get("part", "").strip()   # search by part name
    user_q = request.args.get("user", "").strip()   # search by user
    limit = request.args.get("limit", "50").strip()

    try:
        limit_int = int(limit)
        if limit_int < 1 or limit_int > 500:
            limit_int = 50
    except ValueError:
        limit_int = 50

    conn = get_db_connection()
    cur = conn.cursor()

    sql = """
        SELECT t.*, p.name AS part_name
        FROM transactions t
        JOIN parts p ON p.id = t.part_id
        WHERE 1=1
    """
    params = []

    if t_type in ("issue", "return"):
        sql += " AND t.type = ?"
        params.append(t_type)

    if part_q:
        sql += " AND p.name LIKE ?"
        params.append(f"%{part_q}%")

    if user_q:
        sql += " AND t.user LIKE ?"
        params.append(f"%{user_q}%")

    sql += " ORDER BY t.id DESC LIMIT ?"
    params.append(limit_int)

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    # Part dropdown data
    parts_list = get_parts_with_stock()

    return render_template(
        "transactions.html",
        transactions=rows,
        parts=parts_list,
        filters={"type": t_type, "part": part_q, "user": user_q, "limit": limit_int}
    )


@app.route("/transactions/issue", methods=["POST"])
@login_required
def issue_part():
    part_id = request.form.get("part_id", "").strip()
    quantity = request.form.get("quantity", "").strip()

    try:
        part_id_int = int(part_id)
    except ValueError:
        flash("Invalid part selected.", "danger")
        return redirect(url_for("transactions"))

    try:
        qty = int(quantity)
        if qty <= 0:
            raise ValueError
    except ValueError:
        flash("Quantity must be a positive integer.", "danger")
        return redirect(url_for("transactions"))

    current_stock = get_part_stock(part_id_int)
    if qty > current_stock:
        flash(f"Insufficient stock. Available: {current_stock}", "danger")
        return redirect(url_for("transactions"))

    conn = get_db_connection()
    cur = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO transactions (part_id, user, type, quantity, timestamp)
        VALUES (?, ?, 'issue', ?, ?)
    """, (part_id_int, session["username"], qty, ts))

    conn.commit()
    conn.close()

    flash("Part issued successfully.", "success")
    return redirect(url_for("transactions"))


@app.route("/transactions/return", methods=["POST"])
@login_required
def return_part():
    part_id = request.form.get("part_id", "").strip()
    quantity = request.form.get("quantity", "").strip()

    try:
        part_id_int = int(part_id)
    except ValueError:
        flash("Invalid part selected.", "danger")
        return redirect(url_for("transactions"))

    try:
        qty = int(quantity)
        if qty <= 0:
            raise ValueError
    except ValueError:
        flash("Quantity must be a positive integer.", "danger")
        return redirect(url_for("transactions"))

    # Returning is allowed even if it makes "stock" exceed total_quantity
    # (Depends on organization rules). We'll allow it but you can restrict it.
    conn = get_db_connection()
    cur = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        INSERT INTO transactions (part_id, user, type, quantity, timestamp)
        VALUES (?, ?, 'return', ?, ?)
    """, (part_id_int, session["username"], qty, ts))

    conn.commit()
    conn.close()

    flash("Part returned successfully.", "success")
    return redirect(url_for("transactions"))


# -----------------------------
# CLI / Startup
# -----------------------------
if __name__ == "__main__":
    init_db()
    # Debug True for lab use; set to False in production.
    app.run(debug=True)