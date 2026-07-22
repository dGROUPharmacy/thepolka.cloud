"""Production entry point for ThePolka.Cloud."""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "instance"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "development-only-change-me"),
    DATA_DIR=str(DATA_DIR),
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{DATA_DIR / 'users.db'}",
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

ECOSYSTEM_PAGES = {
    "mail": ("Mail", "Communications, templates, and mail-system work."),
    "resume": ("Résumé Generator", "Professional résumé tools and publishing workflows."),
    "faire": ("FAIRE OS", "Responsible AI experiments and ecosystem research."),
    "cad": ("CAD Experience", "Computer-aided design projects and technical experience."),
    "directory": ("Navigate", "Find resources across ThePolka.Cloud."),
    "store": ("Boutique", "Products, support, and ways to sustain the ecosystem."),
}


def database_connection():
    connection = sqlite3.connect(DATA_DIR / "marketplace.db")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            expertise TEXT NOT NULL,
            content_type TEXT NOT NULL,
            description TEXT NOT NULL,
            rights_confirmed INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    return connection


def audit_snapshot():
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    required = ["/", "/agent", "/ai-marketplace", "/ai-warehouse", "/health"]
    checks = [
        {"name": "Core application routes", "ok": all(route in routes for route in required)},
        {"name": "Production debug mode disabled", "ok": not app.debug},
        {"name": "Persistent data directory available", "ok": DATA_DIR.is_dir()},
        {"name": "Production secret configured", "ok": app.config["SECRET_KEY"] != "development-only-change-me"},
    ]
    return {
        "service": "thepolka.cloud",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(item["ok"] for item in checks) else "attention",
        "checks": checks,
    }


@app.get("/")
def home():
    if request.host.split(":", 1)[0].lower() == "warehouse.thepolka.cloud":
        return ai_warehouse()
    return render_template("index.html", active="home")


@app.get("/ecosystem/<page>")
def ecosystem_page(page):
    if page not in ECOSYSTEM_PAGES:
        return not_found(None)
    title, description = ECOSYSTEM_PAGES[page]
    return render_template("ecosystem.html", active=page, page=page, title=title, description=description)


@app.get("/agent")
def agent_page():
    return render_template("agent.html", active="agent", audit=audit_snapshot())


@app.get("/api/audit")
def audit_api():
    return jsonify(audit_snapshot())


@app.route("/ai-marketplace", methods=["GET", "POST"])
def ai_marketplace():
    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:120]
        expertise = request.form.get("expertise", "").strip()[:120]
        content_type = request.form.get("content_type", "").strip()[:60]
        description = request.form.get("description", "").strip()[:3000]
        rights_confirmed = request.form.get("rights_confirmed") == "yes"
        if not all((title, expertise, content_type, description, rights_confirmed)):
            error = "Complete every field and confirm you have the right to license the submission."
        else:
            with database_connection() as connection:
                connection.execute(
                    "INSERT INTO contributions (title, expertise, content_type, description, rights_confirmed, status, created_at) VALUES (?, ?, ?, ?, 1, 'submitted', ?)",
                    (title, expertise, content_type, description, datetime.now(timezone.utc).isoformat()),
                )
            return redirect(url_for("ai_marketplace", submitted="1"))

    with database_connection() as connection:
        submissions = connection.execute(
            "SELECT title, expertise, content_type, status, created_at FROM contributions ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return render_template(
        "ai_marketplace.html",
        active="marketplace",
        submissions=submissions,
        error=error,
        submitted=request.args.get("submitted") == "1",
    )


@app.get("/ai-warehouse")
def ai_warehouse():
    with database_connection() as connection:
        catalog = connection.execute(
            "SELECT id, title, expertise, content_type, created_at FROM contributions WHERE status = 'accepted' ORDER BY id DESC"
        ).fetchall()
        counts = {
            row["status"]: row["count"]
            for row in connection.execute("SELECT status, COUNT(*) AS count FROM contributions GROUP BY status")
        }
    return render_template("ai_warehouse.html", active="warehouse", catalog=catalog, counts=counts)


@app.get("/health")
def health():
    return jsonify(status="ok", service="thepolka.cloud"), 200


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
