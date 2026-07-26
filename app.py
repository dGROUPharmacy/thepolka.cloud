"""Production entry point for ThePolka.Cloud."""

import os
import sqlite3
import io
import zipfile
import json
import hmac
import time
from collections import defaultdict, deque
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from resume_generator.normalize import normalize
from resume_generator.renderer.markdown import render_markdown
from resume_generator.renderer.html import render_html
from resume_generator.renderer.pdf import render_pdf
from resume_generator.renderer.docx import render_docx


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "instance"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "development-only-change-me"),
    DATA_DIR=str(DATA_DIR),
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{DATA_DIR / 'users.db'}",
    MAX_CONTENT_LENGTH=1_048_576,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

RATE_WINDOWS = defaultdict(deque)
BLOCKED_PROBE_PREFIXES = (
    "/.env", "/.git", "/wp-admin", "/wp-login", "/xmlrpc.php",
    "/phpmyadmin", "/vendor/phpunit", "/cgi-bin", "/actuator",
)


def request_identity():
    forwarded = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",", 1)[0].strip() or request.remote_addr or "unknown")[:80]


def limited(bucket, maximum, seconds):
    now = time.monotonic()
    key = (bucket, request_identity())
    entries = RATE_WINDOWS[key]
    while entries and entries[0] <= now - seconds:
        entries.popleft()
    if len(entries) >= maximum:
        return True
    entries.append(now)
    return False


def admin_authorized():
    expected = os.environ.get("ADMIN_TOKEN", "")
    supplied = request.headers.get("X-Admin-Token", "")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


@app.before_request
def reject_common_probes():
    path = request.path.lower()
    if path.startswith(BLOCKED_PROBE_PREFIXES):
        return Response("Not found", status=404, mimetype="text/plain")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and limited("write", 30, 60):
        return jsonify(error="Too many requests. Try again shortly."), 429


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; connect-src 'self' https://api.weather.gov "
        "https://nominatim.openstreetmap.org; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'self'; form-action 'self'",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if request.path.startswith("/api/") or request.path.startswith("/stripe/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


ECOSYSTEM_PAGES = {
    "mail": ("Mail", "Communications, templates, and mail-system work."),
    "resume": ("Résumé Generator", "Professional résumé tools and publishing workflows."),
    "faire": ("FAIRE OS", "Responsible AI experiments and ecosystem research."),
    "cad": ("CAD Experience", "Computer-aided design projects and technical experience."),
    "directory": ("Navigate", "Find resources across ThePolka.Cloud."),
    "store": ("Boutique", "Products, support, and ways to sustain the ecosystem."),
}

AGENT_PRODUCTS = {
    "base": {"name": "Polka Base Agent", "price": 29, "description": "Core agent runtime, configuration, logging, health checks, and skin loader.", "skills": ["runtime", "logging", "health", "skin-loader"]},
    "spellcheck": {"name": "Editorial / Spell-Check Skin", "price": 39, "description": "Proofreading, spelling, clarity, tone, and consistency review.", "skills": ["spelling", "grammar", "clarity", "tone"]},
    "cybersecurity": {"name": "Cybersecurity Skin", "price": 79, "description": "Defensive configuration review, security headers, dependency checks, and evidence reports.", "skills": ["headers", "dependencies", "configuration", "reporting"]},
    "advertising": {"name": "Advertising Analytics Skin", "price": 59, "description": "Impressions, click volume, redirects, CTR, and campaign-value reporting.", "skills": ["impressions", "clicks", "redirects", "ctr"]},
    "sales": {"name": "Sales Agent Skin", "price": 69, "description": "Lead qualification, offer presentation, checkout routing, and pipeline follow-up.", "skills": ["leads", "offers", "checkout", "pipeline"]},
    "social": {"name": "Social Media Skin", "price": 49, "description": "Channel-ready drafts, calendars, reuse suggestions, and engagement review.", "skills": ["drafting", "calendar", "repurposing", "engagement"]},
    "housekeeping": {"name": "Housekeeping Agent Skin", "price": 89, "description": "Daily audits, safe cache/temp cleanup, route checks, and operational evidence.", "skills": ["daily-audit", "safe-cleanup", "route-checks", "evidence"]},
}

WORK_PLATFORMS = [
    {"name": "Handshake AI", "category": "AI evaluation", "stage": "Active work", "action": "Open workspace", "url": "https://ai.joinhandshake.com/", "note": "Project-based fellowship work; availability varies."},
    {"name": "Outlier", "category": "AI training + coding", "stage": "Assessment", "action": "Open dashboard", "url": "https://app.outlier.ai/", "note": "Complete the Python retake only when your dashboard enables it."},
    {"name": "Mercor", "category": "Technical expert work", "stage": "Sign up", "action": "Create profile", "url": "https://www.mercor.com/", "note": "Technical and research contracts may require matching."},
    {"name": "DataAnnotation", "category": "AI evaluation + coding", "stage": "Sign up", "action": "Create profile", "url": "https://www.dataannotation.tech/", "note": "Work access depends on qualification results and demand."},
    {"name": "Alignerr", "category": "Expert AI evaluation", "stage": "Sign up", "action": "Create profile", "url": "https://www.alignerr.com/", "note": "Subject-area assessments may be required."},
    {"name": "OneForma", "category": "Data + language projects", "stage": "Explore", "action": "Browse projects", "url": "https://www.oneforma.com/", "note": "Project terms and eligibility differ by location."},
    {"name": "TELUS Digital AI", "category": "Search + AI community", "stage": "Explore", "action": "Browse openings", "url": "https://www.telusdigital.com/careers/ai-community", "note": "Availability and contractor classification vary."},
    {"name": "CrowdGen by Appen", "category": "Data collection + evaluation", "stage": "Explore", "action": "Browse projects", "url": "https://crowdgen.com/", "note": "Review each project's pay and requirements before joining."},
]


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


def mail_connection():
    connection = sqlite3.connect(DATA_DIR / "mail.db")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS mailboxes (address TEXT PRIMARY KEY, display_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Active');
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, recipient TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS activity_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, action TEXT NOT NULL, sender TEXT, recipient TEXT, subject TEXT, detail TEXT);
    """)
    seeds = [("andy@alight", "Andy"), ("ericka@northwesternmutual", "Ericka"), ("michelle@amazon", "Michelle"), ("robert@ibm", "Robert"), ("katie@lyft", "Katie"), ("jordan@salesforce", "Jordan"), ("pia@netflix", "Pia"), ("marcus@intuit", "Marcus"), ("lena@stripe", "Lena")]
    connection.executemany("INSERT OR IGNORE INTO mailboxes (address, display_name) VALUES (?, ?)", seeds)
    connection.commit()
    return connection


def audit_connection():
    connection = sqlite3.connect(DATA_DIR / "audit.db")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE IF NOT EXISTS audit_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, checked_at TEXT NOT NULL, status TEXT NOT NULL)"
    )
    return connection


def advertising_connection():
    connection = sqlite3.connect(DATA_DIR / "advertising.db")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS weather_ad_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, created_at TEXT NOT NULL)")
    return connection


def forecast_discussion_connection():
    connection = sqlite3.connect(DATA_DIR / "forecast_discussion.db")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discussion_day TEXT NOT NULL,
        display_name TEXT NOT NULL,
        comment TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    return connection


def mylm_connection():
    connection = sqlite3.connect(DATA_DIR / "mylm.db")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS pilot_intake (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        authored_email_count INTEGER NOT NULL,
        consent_confirmed INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")
    return connection


def ilaw_connection():
    connection = sqlite3.connect(DATA_DIR / "ilaw.db")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        organization TEXT NOT NULL DEFAULT '',
        cohort TEXT NOT NULL,
        terms_confirmed INTEGER NOT NULL,
        payment_status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    )""")
    return connection


def forecast_discussion_day():
    return datetime.now(ZoneInfo("America/Denver")).date().isoformat()


def agent_package(slug):
    product = AGENT_PRODUCTS[slug]
    manifest = {
        "schema": "thepolka.agent/v1",
        "slug": slug,
        "name": product["name"],
        "base": "polka-base-agent",
        "price_usd": product["price"],
        "skills": product["skills"],
        "entrypoint": "agent.py",
    }
    agent_source = f'''"""ThePolka.Cloud {product["name"]} package."""
import json
from pathlib import Path

MANIFEST = {manifest!r}

def run(payload=None):
    """Return an inspectable execution record; connect approved tools in config.json."""
    return {{"agent": MANIFEST["slug"], "status": "ready", "payload": payload or {{}}, "skills": MANIFEST["skills"]}}

if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
'''
    return manifest, agent_source


def recent_audits():
    with audit_connection() as connection:
        rows = connection.execute(
            "SELECT checked_at, status FROM audit_runs ORDER BY id DESC LIMIT 5"
        ).fetchall()
    return [dict(row) for row in rows]


def audit_snapshot(record=False):
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    required = ["/", "/tools", "/faire/trial/download", "/agent", "/agentforce", "/java", "/ai-marketplace", "/ai-warehouse", "/health"]
    checks = [
        {"name": "Core application routes", "ok": all(route in routes for route in required)},
        {"name": "Production debug mode disabled", "ok": not app.debug},
        {"name": "Persistent data directory available", "ok": DATA_DIR.is_dir()},
        {"name": "Production secret configured", "ok": app.config["SECRET_KEY"] != "development-only-change-me"},
    ]
    snapshot = {
        "service": "thepolka.cloud",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(item["ok"] for item in checks) else "attention",
        "checks": checks,
    }
    if record:
        with audit_connection() as connection:
            connection.execute(
                "INSERT INTO audit_runs (checked_at, status) VALUES (?, ?)",
                (snapshot["checked_at"], snapshot["status"]),
            )
            connection.execute(
                "DELETE FROM audit_runs WHERE id NOT IN (SELECT id FROM audit_runs ORDER BY id DESC LIMIT 100)"
            )
    return snapshot


@app.get("/")
def home():
    hostname = request.host.split(":", 1)[0].lower()
    if hostname == "warehouse.thepolka.cloud":
        return ai_warehouse()
    if hostname == "agentforce.thepolka.cloud":
        return agentforce_page()
    if hostname == "apply.thepolka.cloud":
        return apply_page()
    if hostname == "mylm.thepolka.cloud":
        return mylm_page()
    if hostname == "ilaw.thepolka.cloud":
        return ilaw_page()
    if hostname == "profile.thepolka.cloud":
        return profile_page()
    if hostname == "java.thepolka.cloud":
        return java_page()
    return render_template("index.html", active="home")


@app.get("/apply")
def apply_page():
    return render_template("apply.html", active="apply", platforms=WORK_PLATFORMS)


@app.get("/mylm")
def mylm_page():
    return render_template("mylm.html", active="mylm")


@app.get("/ilaw")
def ilaw_page():
    return render_template("ilaw.html", active="ilaw")


@app.get("/profile")
def profile_page():
    return render_template("profile.html", active="profile")


@app.get("/java")
def java_page():
    return render_template("java.html", active="java")


@app.get("/tools")
def tools_page():
    return render_template("tools.html", active="tools")


@app.get("/faire/trial/download")
def faire_trial_download():
    bundle = io.BytesIO()
    trial_directory = BASE_DIR / "faire_trial"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(trial_directory.iterdir()):
            if path.is_file():
                archive.write(path, f"Faire-Windows-Trial/{path.name}")
    bundle.seek(0)
    return send_file(bundle, mimetype="application/zip", as_attachment=True, download_name="faire-windows-offline-trial.zip")


@app.post("/ilaw/register")
def ilaw_register():
    full_name = request.form.get("full_name", "").strip()[:120]
    email = request.form.get("email", "").strip().lower()[:200]
    organization = request.form.get("organization", "").strip()[:160]
    cohort = request.form.get("cohort", "Founding Cohort").strip()[:80]
    terms = request.form.get("terms") == "on"
    if not full_name or "@" not in email or not terms:
        return redirect(url_for("ilaw_page", registration="incomplete") + "#enroll")
    with ilaw_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO registrations
               (full_name, email, organization, cohort, terms_confirmed, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (full_name, email, organization, cohort, datetime.now(timezone.utc).isoformat()),
        )
        registration_id = cursor.lastrowid
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    price_id = os.environ.get("STRIPE_PRICE_ILAW_CERTIFICATE", "")
    if not secret or not price_id:
        return redirect(url_for("ilaw_page", registration="saved", checkout="configuration-required") + "#enroll")
    body = urlencode({
        "mode": "payment",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": 1,
        "customer_email": email,
        "success_url": request.url_root.rstrip("/") + url_for("ilaw_page") + "?enrollment=paid#enroll",
        "cancel_url": request.url_root.rstrip("/") + url_for("ilaw_page") + "?enrollment=cancelled#enroll",
        "metadata[product]": "ilaw-ai-law-certificate",
        "metadata[registration_id]": registration_id,
        "metadata[student_name]": full_name,
    }).encode()
    stripe_request = Request("https://api.stripe.com/v1/checkout/sessions", data=body, headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(stripe_request, timeout=20) as response:
            session = json.load(response)
        return redirect(session["url"], code=303)
    except Exception:
        app.logger.exception("iLAW Stripe Checkout creation failed")
        return redirect(url_for("ilaw_page", registration="saved", checkout="failed") + "#enroll")


@app.get("/privacy")
def privacy_page():
    return render_template("privacy.html", active="privacy")


@app.post("/api/mylm/intake")
def mylm_intake():
    raw = request.get_json(silent=True) or request.form
    email = str(raw.get("email", "")).strip().lower()
    try:
        authored_count = int(raw.get("authored_email_count", 0))
    except (TypeError, ValueError):
        authored_count = 0
    consent = str(raw.get("consent", "")).lower() in {"1", "true", "on", "yes"}
    if "@" not in email or authored_count < 1000 or not consent:
        return jsonify(error="A valid email, at least 1,000 authored emails, and consent confirmation are required."), 400
    with mylm_connection() as connection:
        connection.execute(
            "INSERT INTO pilot_intake (email, authored_email_count, consent_confirmed, created_at) VALUES (?, ?, 1, ?)",
            (email, authored_count, datetime.now(timezone.utc).isoformat()),
        )
    return jsonify(status="accepted", message="Pilot request saved. The separate consented email-selection and upload step comes next.", pilot_payment_usd=1)


@app.get("/ecosystem/<page>")
def ecosystem_page(page):
    if page not in ECOSYSTEM_PAGES:
        return not_found(None)
    if page == "resume":
        return render_template("resume_generator.html", active="resume")
    if page == "mail":
        return render_template("mail.html", active="mail")
    if page == "cad":
        model_path = BASE_DIR / "static" / "model" / "stand.glb"
        cad_error = None
        if not model_path.exists():
            try:
                from static.scripts.generate_stand import main as generate_stand
                generate_stand()
            except Exception as exc:
                app.logger.exception("CAD asset generation failed")
                cad_error = str(exc)
        return render_template("cad.html", active="cad", cad_error=cad_error)
    if page == "faire":
        return render_template("faire.html", active="faire")
    if page == "directory":
        return render_template("directory.html", active="directory")
    title, description = ECOSYSTEM_PAGES[page]
    return render_template("ecosystem.html", active=page, page=page, title=title, description=description)


@app.post("/api/resume-generator")
def generate_resume():
    raw = request.get_json(silent=True) or {}
    if not raw:
        return jsonify(error="No résumé data received"), 400
    data = normalize(raw)
    if not data["name"]:
        return jsonify(error="A name is required"), 400
    name_slug = data["name"].replace(" ", "_").replace("/", "-")
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{name_slug}_resume.md", render_markdown(data).encode("utf-8"))
        archive.writestr(f"{name_slug}_resume.html", render_html(data).encode("utf-8"))
        archive.writestr(f"{name_slug}_resume.pdf", render_pdf(data))
        archive.writestr(f"{name_slug}_resume.docx", render_docx(data))
    bundle.seek(0)
    return send_file(bundle, mimetype="application/zip", as_attachment=True, download_name=f"{name_slug}_resume_bundle.zip")


@app.get("/api/mailboxes")
def mailboxes_api():
    with mail_connection() as db:
        return jsonify([dict(row) for row in db.execute("SELECT address, display_name, status FROM mailboxes ORDER BY address")])


@app.get("/api/inbox/<path:address>")
def inbox_api(address):
    with mail_connection() as db:
        rows = db.execute("SELECT id, sender, recipient, subject, body, created_at, read FROM messages WHERE recipient=? ORDER BY id DESC", (address,)).fetchall()
        return jsonify([dict(row) for row in rows])


@app.get("/api/activity")
def activity_api():
    with mail_connection() as db:
        rows = db.execute("SELECT timestamp, action, sender, recipient, subject, detail FROM activity_log ORDER BY id DESC LIMIT 50").fetchall()
        return jsonify([dict(row) for row in rows])


@app.post("/api/send")
def send_mail_api():
    if not admin_authorized():
        return jsonify(error="Administrative authorization required."), 403
    data = request.get_json(silent=True) or {}
    sender, recipient = str(data.get("sender", "")).strip(), str(data.get("recipient", "")).strip()
    if not sender or not recipient:
        return jsonify(error="Sender and recipient are required"), 400
    with mail_connection() as db:
        known = db.execute("SELECT COUNT(*) FROM mailboxes WHERE address IN (?, ?)", (sender, recipient)).fetchone()[0]
        if known != 2:
            return jsonify(error="Unknown mailbox"), 400
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        subject, body = str(data.get("subject", ""))[:200], str(data.get("body", ""))[:10000]
        db.execute("INSERT INTO messages (sender, recipient, subject, body, created_at) VALUES (?, ?, ?, ?, ?)", (sender, recipient, subject, body, timestamp))
        db.execute("INSERT INTO activity_log (timestamp, action, sender, recipient, subject, detail) VALUES (?, 'delivered', ?, ?, ?, 'Message routed to recipient inbox.')", (timestamp, sender, recipient, subject))
    return jsonify(status="delivered")


@app.post("/api/read/<int:message_id>")
def mark_mail_read_api(message_id):
    if not admin_authorized():
        return jsonify(error="Administrative authorization required."), 403
    with mail_connection() as db:
        db.execute("UPDATE messages SET read=1 WHERE id=?", (message_id,))
    return jsonify(status="ok")


@app.get("/agent")
def agent_page():
    audit = audit_snapshot(record=True)
    return render_template("agent.html", active="agent", audit=audit, history=recent_audits())


@app.get("/agentforce")
def agentforce_page():
    return render_template("agentforce.html", active="agentforce", products=AGENT_PRODUCTS)


@app.get("/agentforce/download/<slug>")
def agent_download(slug):
    if slug not in AGENT_PRODUCTS:
        return not_found(None)
    manifest, source = agent_package(slug)
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("agent.py", source)
        archive.writestr("config.example.json", json.dumps({"enabled": True, "schedule": "manual", "tools": []}, indent=2))
        archive.writestr("README.md", f"# {manifest['name']}\n\nLoad this skin with the Polka Base Agent. Review permissions before connecting tools.\n")
    bundle.seek(0)
    return send_file(bundle, mimetype="application/zip", as_attachment=True, download_name=f"thepolka-{slug}-agent.zip")


@app.post("/agentforce/checkout/<slug>")
def agent_checkout(slug):
    if slug not in AGENT_PRODUCTS:
        return not_found(None)
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    price_id = os.environ.get(f"STRIPE_PRICE_{slug.upper()}", "")
    if not secret or not price_id:
        return redirect(url_for("agentforce_page", checkout="configuration-required") + f"#{slug}")
    body = urlencode({
        "mode": "payment",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": 1,
        "success_url": request.url_root.rstrip("/") + url_for("agentforce_page") + f"?purchased={slug}#{slug}",
        "cancel_url": request.url_root.rstrip("/") + url_for("agentforce_page") + f"?cancelled={slug}#{slug}",
        "metadata[agent_slug]": slug,
    }).encode()
    stripe_request = Request("https://api.stripe.com/v1/checkout/sessions", data=body, headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(stripe_request, timeout=20) as response:
            session = json.load(response)
        return redirect(session["url"], code=303)
    except Exception:
        app.logger.exception("Stripe Checkout creation failed")
        return redirect(url_for("agentforce_page", checkout="failed") + f"#{slug}")


@app.post("/faire/checkout")
def faire_checkout():
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    price_id = os.environ.get("STRIPE_PRICE_FAIRE_DESKTOP", "")
    if not secret or not price_id:
        return redirect(url_for("ecosystem_page", page="faire", checkout="configuration-required") + "#purchase")
    body = urlencode({
        "mode": "payment",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": 1,
        "success_url": request.url_root.rstrip("/") + url_for("ecosystem_page", page="faire") + "?purchased=faire-desktop#purchase",
        "cancel_url": request.url_root.rstrip("/") + url_for("ecosystem_page", page="faire") + "?cancelled=faire-desktop#purchase",
        "metadata[product]": "faire-desktop",
    }).encode()
    stripe_request = Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=body,
        headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(stripe_request, timeout=20) as response:
            session = json.load(response)
        return redirect(session["url"], code=303)
    except Exception:
        app.logger.exception("Faire Desktop Stripe Checkout creation failed")
        return redirect(url_for("ecosystem_page", page="faire", checkout="failed") + "#purchase")


@app.post("/api/housekeeping/run")
def housekeeping_run():
    if not admin_authorized():
        return jsonify(error="Administrative authorization required."), 403
    removed = []
    cutoff = datetime.now(timezone.utc).timestamp() - (7 * 86400)
    for path in DATA_DIR.glob("*.tmp"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path.name)
    snapshot = audit_snapshot(record=True)
    return jsonify(status="complete", removed=removed, audit=snapshot)


@app.get("/api/audit")
def audit_api():
    snapshot = audit_snapshot(record=True)
    snapshot["recent_runs"] = recent_audits()
    return jsonify(snapshot)


@app.post("/api/chat")
def faire_chat_api():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify(error="Write a message first."), 400
    return jsonify(
        reply="FAIRE is online in local-first demonstration mode. Connect an approved hosted or local model to enable generated responses."
    )


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


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nAllow: /\nSitemap: https://thepolka.cloud/sitemap.xml\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    paths = [
        "/", "/forecast", "/tools", "/apply", "/mylm", "/ilaw", "/java",
        "/ecosystem/resume", "/ecosystem/cad", "/ecosystem/faire",
        "/agent", "/agentforce", "/ai-marketplace", "/ai-warehouse", "/privacy",
    ]
    urls = "".join(f"<url><loc>https://thepolka.cloud{path}</loc></url>" for path in paths)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', mimetype="application/xml")


@app.get("/forecast")
def forecast_page():
    return render_template("forecast.html", active="forecast")


def nws_json(url):
    headers = {"User-Agent": "ThePolka.Cloud Forecast (info@thepolka.cloud)", "Accept": "application/geo+json, application/json"}
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


@app.get("/api/forecast")
def forecast_api():
    try:
        forecast = nws_json("https://api.weather.gov/gridpoints/MKX/82,72/forecast")
        period = forecast["properties"]["periods"][0]
        return jsonify(period=period)
    except Exception as exc:
        app.logger.exception("Weather data request failed")
        return jsonify(error="Weather data is temporarily unavailable.", detail=str(exc)), 502


@app.get("/api/forecast/search")
def forecast_search_api():
    query = " ".join(request.args.get("q", "").strip().split())[:100]
    if len(query) < 2:
        return jsonify(error="Enter a city, state, ZIP code, or place name."), 400
    try:
        geocode_url = "https://nominatim.openstreetmap.org/search?" + urlencode({"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"})
        locations = nws_json(geocode_url)
        if not locations:
            return jsonify(error="Location not found. Try a city and state or ZIP code."), 404
        latitude, longitude = float(locations[0]["lat"]), float(locations[0]["lon"])
        point = nws_json(f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}")
        forecast = nws_json(point["properties"]["forecast"])
        return jsonify(location=locations[0]["display_name"], latitude=latitude, longitude=longitude, period=forecast["properties"]["periods"][0])
    except Exception as exc:
        app.logger.exception("Local forecast search failed")
        return jsonify(error="Local forecast search is temporarily unavailable.", detail=str(exc)), 502


@app.route("/api/forecast/discussion", methods=["GET", "POST"])
def forecast_discussion_api():
    day = forecast_discussion_day()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = " ".join(str(data.get("name", "")).strip().split())[:40]
        comment = " ".join(str(data.get("comment", "")).strip().split())[:500]
        if not name or not comment:
            return jsonify(error="A display name and comment are required."), 400
        if str(data.get("website", "")).strip():
            return jsonify(status="received"), 202
        with forecast_discussion_connection() as connection:
            recent = connection.execute(
                "SELECT created_at FROM comments WHERE discussion_day=? AND lower(display_name)=lower(?) ORDER BY id DESC LIMIT 1",
                (day, name),
            ).fetchone()
            if recent:
                last = datetime.fromisoformat(recent["created_at"])
                if (datetime.now(timezone.utc) - last).total_seconds() < 60:
                    return jsonify(error="Please wait one minute before commenting again."), 429
            connection.execute(
                "INSERT INTO comments (discussion_day, display_name, comment, created_at) VALUES (?, ?, ?, ?)",
                (day, name, comment, datetime.now(timezone.utc).isoformat()),
            )
    with forecast_discussion_connection() as connection:
        rows = connection.execute(
            "SELECT id, display_name, comment, created_at FROM comments WHERE discussion_day=? ORDER BY id ASC LIMIT 100",
            (day,),
        ).fetchall()
    return jsonify(day=day, refresh_timezone="America/Denver", comments=[dict(row) for row in rows])


@app.post("/api/forecast/ad-event")
def forecast_ad_event():
    event = str((request.get_json(silent=True) or {}).get("event", ""))
    if event not in {"impression", "click"}:
        return jsonify(error="Invalid event"), 400
    with advertising_connection() as connection:
        connection.execute("INSERT INTO weather_ad_events (event, created_at) VALUES (?, ?)", (event, datetime.now(timezone.utc).isoformat()))
    return jsonify(status="recorded", event=event)


@app.get("/api/forecast/ad-metrics")
def forecast_ad_metrics():
    with advertising_connection() as connection:
        counts = {row["event"]: row["count"] for row in connection.execute("SELECT event, COUNT(*) AS count FROM weather_ad_events GROUP BY event")}
    impressions, clicks = counts.get("impression", 0), counts.get("click", 0)
    return jsonify(impressions=impressions, clicks=clicks, click_through_rate=(clicks / impressions if impressions else 0))


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
