# Inventory Management System (Flask + SQLite)

Intermediate-level inventory management web app suitable for a college lab or small organization.

## Features
- Authentication (Flask sessions)
- Password hashing via `werkzeug.security`
- Roles: **Admin** and **User**
- Parts management (Admin can add/edit/delete)
- Transactions: issue/return with user + timestamp
- Stock calculated dynamically (not stored):
  `stock = total_quantity - issued + returned`
- Dashboard: total parts, low stock, recent transactions
- Search parts by name
- Filter transaction history
- Bootstrap 5 UI + flash messages

## Project Structure
```
inventory-system/
  app.py
  database.db           # auto-created
  requirements.txt
  README.md

  templates/
    base.html
    login.html
    dashboard.html
    parts.html
    transactions.html

  static/
    style.css
    script.js
```

## Setup Instructions

### 1) Create a virtual environment (recommended)
```bash
python -m venv venv
```

Activate it:

**Windows (PowerShell)**
```bash
venv\Scripts\Activate.ps1
```

**macOS/Linux**
```bash
source venv/bin/activate
```

### 2) Install requirements
```bash
pip install -r requirements.txt
```

### 3) Run the app
```bash
python app.py
```

The app will start in debug mode and create `database.db` automatically.

Open:
- http://127.0.0.1:5000

## Default Admin Login (first run)
- Username: `admin`
- Password: `admin123`

**Important:** For real use, change the secret key in `app.py` and create new users (you can extend the app with a user management page).

## Notes / Customization
- Low-stock threshold is set in `app.py`:
  `LOW_STOCK_THRESHOLD = 5`
- Deleting a part is blocked if it has any transaction history (to preserve referential meaning).