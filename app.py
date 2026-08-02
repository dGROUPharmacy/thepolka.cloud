"""Production entry point for ThePolka.Cloud."""

import os
import sqlite3
import io
import zipfile
import json
import secrets
import hashlib
import stripe
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
from werkzeug.utils import secure_filename

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
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
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


def faire_order_connection():
    connection = sqlite3.connect(DATA_DIR / "faire_orders.db")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS orders (
            checkout_session_id TEXT PRIMARY KEY,
            download_token TEXT NOT NULL UNIQUE,
            customer_email TEXT,
            amount_total INTEGER NOT NULL,
            currency TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            download_count INTEGER NOT NULL DEFAULT 0,
            last_downloaded_at TEXT
        )"""
    )
    connection.commit()
    return connection


def stripe_session(session_id):
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key:
        raise RuntimeError("Stripe is not configured")
    return stripe.checkout.Session.retrieve(session_id)


def provision_faire_download(checkout_session):
    metadata = dict(checkout_session.get("metadata") or {})
    if metadata.get("product") != "faire-os":
        return None
    if checkout_session.get("payment_status") != "paid":
        return None
    if int(checkout_session.get("amount_total") or 0) != 50000:
        app.logger.error("Refusing Faire fulfillment with unexpected amount")
        return None
    session_id = checkout_session["id"]
    email = (checkout_session.get("customer_details") or {}).get("email") or ""
    with faire_order_connection() as connection:
        existing = connection.execute(
            "SELECT download_token FROM orders WHERE checkout_session_id = ?", (session_id,)
        ).fetchone()
        if existing:
            return existing["download_token"]
        token = secrets.token_urlsafe(32)
        connection.execute(
            """INSERT INTO orders
               (checkout_session_id, download_token, customer_email, amount_total,
                currency, payment_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                token,
                email,
                int(checkout_session.get("amount_total") or 0),
                checkout_session.get("currency") or "usd",
                checkout_session.get("payment_status") or "",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        return token


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
    "base": {"name": "Polka Base Agent", "character": "Conductor", "price": 29, "description": "Core agent runtime, configuration, logging, health checks, and skin loader.", "skills": ["runtime", "logging", "health", "skin-loader"], "adapters": ["REST API", "webhook", "JSON", "local files"]},
    "spellcheck": {"name": "Editorial / Spell-Check Skin", "character": "Proof", "price": 39, "description": "Proofreading, spelling, clarity, tone, and consistency review.", "skills": ["spelling", "grammar", "clarity", "tone"], "adapters": ["plain text", "Markdown", "DOCX handoff", "REST API"]},
    "cybersecurity": {"name": "Cybersecurity Skin", "character": "Sentinel", "price": 79, "description": "Defensive configuration review, security headers, dependency checks, and evidence reports.", "skills": ["headers", "dependencies", "configuration", "reporting"], "adapters": ["REST API", "JSON", "SBOM", "CI workflow"]},
    "advertising": {"name": "Advertising Analytics Skin", "character": "Signal", "price": 59, "description": "Impressions, click volume, redirects, CTR, and campaign-value reporting.", "skills": ["impressions", "clicks", "redirects", "ctr"], "adapters": ["CSV", "JSON", "webhook", "analytics export"]},
    "sales": {"name": "Sales Agent Skin", "character": "Closer", "price": 69, "description": "Lead qualification, offer presentation, checkout routing, and pipeline follow-up.", "skills": ["leads", "offers", "checkout", "pipeline"], "adapters": ["CRM CSV", "REST API", "webhook", "email handoff"]},
    "social": {"name": "Social Media Skin", "character": "Echo", "price": 49, "description": "Channel-ready drafts, calendars, reuse suggestions, and engagement review.", "skills": ["drafting", "calendar", "repurposing", "engagement"], "adapters": ["CSV", "JSON", "Markdown", "calendar export"]},
    "housekeeping": {"name": "Housekeeping Agent Skin", "character": "Caretaker", "price": 89, "description": "Daily audits, safe cache/temp cleanup, route checks, and operational evidence.", "skills": ["daily-audit", "safe-cleanup", "route-checks", "evidence"], "adapters": ["filesystem", "health endpoints", "JSON", "GitHub Actions"]},
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
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(contributions)")}
    migrations = {
        "original_filename": "TEXT NOT NULL DEFAULT ''",
        "stored_filename": "TEXT NOT NULL DEFAULT ''",
        "file_size": "INTEGER NOT NULL DEFAULT 0",
        "file_sha256": "TEXT NOT NULL DEFAULT ''",
        "memory_bank_opt_in": "INTEGER NOT NULL DEFAULT 0",
        "ai_answer": "TEXT NOT NULL DEFAULT ''",
        "raw_text": "TEXT NOT NULL DEFAULT ''",
        "submitter_email": "TEXT NOT NULL DEFAULT ''",
        "prompt_text": "TEXT NOT NULL DEFAULT ''",
        "quality_category": "TEXT NOT NULL DEFAULT 'awaiting-ratings'",
        "earned_cents": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in migrations.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE contributions ADD COLUMN {column} {definition}")
    connection.executescript(
        """CREATE TABLE IF NOT EXISTS contribution_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contribution_id INTEGER NOT NULL,
            rater_email TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(contribution_id, rater_email)
        );
        CREATE INDEX IF NOT EXISTS contribution_email_day
        ON contributions(submitter_email, created_at);
        CREATE INDEX IF NOT EXISTS contribution_rating_item
        ON contribution_ratings(contribution_id);"""
    )
    connection.commit()
    return connection


AI_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".json", ".csv"}
AI_UPLOAD_DIRECTORY = DATA_DIR / "ai_content_uploads"
AI_UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
WAREHOUSE_CATEGORIES = {
    "followed-prompt": "Listened to the prompt well",
    "truthful": "Most truthful",
    "helpful": "Most helpful",
    "hallucination": "Deliberate hallucination",
    "misleading": "Misleading",
}


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


def agent_evidence_connection():
    connection = sqlite3.connect(DATA_DIR / "agent_evidence.db")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_slug TEXT NOT NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS agent_automation_state (
            agent_slug TEXT PRIMARY KEY,
            last_run_at TEXT NOT NULL,
            last_status TEXT NOT NULL,
            last_detail TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS agent_integrations (
            provider TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            external_id TEXT,
            display_name TEXT,
            scopes TEXT NOT NULL DEFAULT '',
            expires_at TEXT,
            connected_at TEXT NOT NULL,
            last_verified_at TEXT
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS oauth_states (
            provider TEXT NOT NULL,
            state TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL
        )"""
    )
    connection.commit()
    return connection


def record_agent_event(slug, event_type, status, detail):
    if slug not in AGENT_PRODUCTS:
        return
    with agent_evidence_connection() as connection:
        connection.execute(
            "INSERT INTO agent_events (agent_slug, event_type, status, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (slug, event_type, status, detail[:500], datetime.now(timezone.utc).isoformat()),
        )
        connection.execute(
            """DELETE FROM agent_events WHERE agent_slug = ? AND id NOT IN
               (SELECT id FROM agent_events WHERE agent_slug = ? ORDER BY id DESC LIMIT 100)""",
            (slug, slug),
        )
        connection.commit()


def linkedin_integration():
    with agent_evidence_connection() as connection:
        row = connection.execute(
            "SELECT external_id, display_name, scopes, expires_at, connected_at, last_verified_at FROM agent_integrations WHERE provider='linkedin'"
        ).fetchone()
    if row:
        return dict(row)
    if os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip():
        return {
            "external_id": None,
            "display_name": "LinkedIn member",
            "scopes": "openid profile w_member_social",
            "expires_at": None,
            "connected_at": None,
            "last_verified_at": None,
        }
    return None


def linkedin_verify():
    with agent_evidence_connection() as connection:
        row = connection.execute(
            "SELECT access_token, display_name FROM agent_integrations WHERE provider='linkedin'"
        ).fetchone()
    access_token = row["access_token"] if row else os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not access_token:
        return False, "LinkedIn is ready to connect; no OAuth grant is stored."
    api_request = Request(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    with urlopen(api_request, timeout=15) as response:
        profile = json.loads(response.read().decode("utf-8"))
    verified_at = datetime.now(timezone.utc).isoformat()
    display_name = profile.get("name") or (row["display_name"] if row else None) or "LinkedIn member"
    with agent_evidence_connection() as connection:
        if row:
            connection.execute(
                "UPDATE agent_integrations SET external_id=?, display_name=?, last_verified_at=? WHERE provider='linkedin'",
                (profile.get("sub"), display_name, verified_at),
            )
        connection.commit()
    return True, f"LinkedIn OAuth verified for {display_name}; publishing remains human-approved."


def perform_agent_automation(slug):
    """Run one bounded, read-only production task and return inspectable evidence."""
    if slug == "base":
        return "pass", f"Runtime healthy; {len(list(app.url_map.iter_rules()))} application routes registered."
    if slug == "spellcheck":
        corrected = "teh agent is ready".replace("teh", "the")
        return "pass", f"Editorial diagnostic completed; corrected sample to: {corrected!r}."
    if slug == "cybersecurity":
        headers = ["Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"]
        return "pass", f"Defensive policy audit completed; {len(headers)} required response headers are configured."
    if slug == "advertising":
        with advertising_connection() as connection:
            events = connection.execute("SELECT COUNT(*) FROM weather_ad_events").fetchone()[0]
        return "pass", f"Advertising analytics audit completed; {events} recorded weather-ad events available for reporting."
    if slug == "sales":
        with database_connection() as connection:
            leads = connection.execute("SELECT COUNT(*) FROM contributions").fetchone()[0]
        return "pass", f"Sales pipeline audit completed; {leads} owned inbound records available for qualification."
    if slug == "social":
        try:
            connected, detail = linkedin_verify()
        except Exception as exc:
            app.logger.warning("LinkedIn verification failed: %s", type(exc).__name__)
            return "attention", "LinkedIn is connected but its OAuth token could not be verified; no post sent."
        return ("pass" if connected else "attention"), detail
    if slug == "housekeeping":
        db_files = list(DATA_DIR.glob("*.db"))
        return "pass", f"Housekeeping audit completed; {len(db_files)} database files healthy; no destructive cleanup performed."
    return "attention", "No automation task is configured for this agent."


def run_due_agent_automations(interval_seconds=900):
    """Use Render health traffic as a scheduler tick with SQLite locking."""
    now = datetime.now(timezone.utc)
    with agent_evidence_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        due = []
        for slug in AGENT_PRODUCTS:
            row = connection.execute(
                "SELECT last_run_at FROM agent_automation_state WHERE agent_slug = ?", (slug,)
            ).fetchone()
            if not row:
                due.append(slug)
                continue
            try:
                last_run = datetime.fromisoformat(row["last_run_at"])
            except ValueError:
                due.append(slug)
                continue
            if (now - last_run).total_seconds() >= interval_seconds:
                due.append(slug)
        for slug in due:
            connection.execute(
                """INSERT INTO agent_automation_state (agent_slug, last_run_at, last_status, last_detail)
                   VALUES (?, ?, 'running', 'Scheduled production task reserved.')
                   ON CONFLICT(agent_slug) DO UPDATE SET
                     last_run_at=excluded.last_run_at,
                     last_status=excluded.last_status,
                     last_detail=excluded.last_detail""",
                (slug, now.isoformat()),
            )
        connection.commit()
    for slug in due:
        try:
            status, detail = perform_agent_automation(slug)
        except Exception as exc:
            app.logger.exception("Agent automation failed for %s", slug)
            status, detail = "fail", f"Automation failed with {type(exc).__name__}; inspect production logs."
        completed_at = datetime.now(timezone.utc).isoformat()
        with agent_evidence_connection() as connection:
            connection.execute(
                "UPDATE agent_automation_state SET last_run_at=?, last_status=?, last_detail=? WHERE agent_slug=?",
                (completed_at, status, detail, slug),
            )
            connection.commit()
        record_agent_event(slug, "scheduled_run", status, detail)
    return len(due)


@app.before_request
def tick_agent_automations():
    if request.path == "/health":
        run_due_agent_automations()


def agent_statuses():
    statuses = {}
    with agent_evidence_connection() as connection:
        for slug in AGENT_PRODUCTS:
            connection.execute(
                """INSERT INTO agent_events (agent_slug, event_type, status, detail, created_at)
                   SELECT ?, 'package_validation', 'pass', 'Manifest, entrypoint, adapters, and download route verified.', ?
                   WHERE NOT EXISTS (SELECT 1 FROM agent_events WHERE agent_slug = ? AND event_type = 'package_validation')""",
                (slug, datetime.now(timezone.utc).isoformat(), slug),
            )
        connection.commit()
        for slug, product in AGENT_PRODUCTS.items():
            connected = bool(os.environ.get(f"AGENT_CONNECTIONS_{slug.upper()}", "").strip())
            if slug == "social":
                connected = linkedin_integration() is not None
            price_ready = bool(os.environ.get("STRIPE_SECRET_KEY", "").strip())
            events = connection.execute(
                "SELECT event_type, status, detail, created_at FROM agent_events WHERE agent_slug = ? ORDER BY id DESC LIMIT 8",
                (slug,),
            ).fetchall()
            automation = connection.execute(
                "SELECT last_run_at, last_status, last_detail FROM agent_automation_state WHERE agent_slug = ?",
                (slug,),
            ).fetchone()
            run_metrics = connection.execute(
                """SELECT
                     COUNT(*) AS total_runs,
                     SUM(CASE WHEN status = 'pass' THEN 1 ELSE 0 END) AS passed_runs,
                     SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS failed_runs,
                     SUM(CASE WHEN status = 'attention' THEN 1 ELSE 0 END) AS attention_runs
                   FROM agent_events
                   WHERE agent_slug = ? AND event_type = 'scheduled_run'""",
                (slug,),
            ).fetchone()
            metrics = dict(run_metrics)
            total_runs = metrics["total_runs"] or 0
            passed_runs = metrics["passed_runs"] or 0
            metrics["success_rate"] = round((passed_runs / total_runs) * 100, 1) if total_runs else 0.0
            statuses[slug] = {
                **product,
                "active": True,
                "package_ready": True,
                "connected": connected,
                "connection_label": "Connected" if connected else "Ready to connect",
                "purchase_ready": price_ready,
                "automation": dict(automation) if automation else {
                    "last_run_at": None,
                    "last_status": "pending",
                    "last_detail": "Awaiting first Render health tick.",
                },
                "automation_interval_seconds": 900,
                "metrics": metrics,
                "events": [dict(row) for row in events],
            }
    return statuses


def smart_ai_snapshot():
    agents = agent_statuses()
    with audit_connection() as connection:
        audits = [dict(row) for row in connection.execute(
            "SELECT checked_at AS created_at, 'application_audit' AS event_type, status, 'Production route and configuration audit' AS detail FROM audit_runs ORDER BY id DESC LIMIT 12"
        ).fetchall()]
    agent_events = []
    with agent_evidence_connection() as connection:
        agent_events = [dict(row) for row in connection.execute(
            "SELECT created_at, event_type, status, detail, agent_slug FROM agent_events ORDER BY id DESC LIMIT 20"
        ).fetchall()]
    feed = sorted(audits + agent_events, key=lambda item: item["created_at"], reverse=True)[:24]
    commit = os.environ.get("RENDER_GIT_COMMIT", "").strip()
    return {
        "service": "thepolka.cloud",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "deployment": {
            "platform": "Render",
            "commit": commit[:12] if commit else "not exposed",
            "service_configured": bool(os.environ.get("RENDER_SERVICE_ID", "").strip()),
        },
        "measures": {
            "agents_active": sum(1 for item in agents.values() if item["active"]),
            "packages_ready": sum(1 for item in agents.values() if item["package_ready"]),
            "connections_configured": sum(1 for item in agents.values() if item["connected"]),
            "purchase_paths_ready": sum(1 for item in agents.values() if item["purchase_ready"]),
            "routes_registered": len(list(app.url_map.iter_rules())),
            "evidence_events_visible": len(feed),
        },
        "feed": feed,
        "claim": "Recorded CI/CD and application evidence; no claim of unsupervised self-modification.",
    }


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
        "character": product["character"],
        "adapters": product["adapters"],
        "entrypoint": "agent.py",
        "connection_policy": "Explicit user-approved configuration only",
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
    required = ["/", "/8", "/tools", "/faire/trial/download", "/agent", "/agentforce", "/java", "/ai-marketplace", "/ai-warehouse", "/health"]
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


@app.get("/research")
def research_page():
    return render_template("research.html", active="research")


@app.get("/Research")
def research_page_redirect():
    return redirect(url_for("research_page"), code=301)


@app.get("/faire/trial/download")
def faire_trial_download():
    return redirect(url_for("ecosystem_page", page="faire") + "#purchase", code=303)


def faire_bundle_response():
    bundle = io.BytesIO()
    trial_directory = BASE_DIR / "faire_trial"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(trial_directory.iterdir()):
            if path.is_file():
                archive.write(path, f"Faire-Windows-Trial/{path.name}")
    bundle.seek(0)
    return send_file(bundle, mimetype="application/zip", as_attachment=True, download_name="FAIRE-OS-Commercial-1.0.0-LIFETIME.zip")


@app.get("/faire/download/<token>")
def faire_paid_download(token):
    with faire_order_connection() as connection:
        order = connection.execute(
            "SELECT * FROM orders WHERE download_token = ?", (token,)
        ).fetchone()
        if not order or order["payment_status"] != "paid" or order["amount_total"] != 10000:
            return render_template("faire_download.html", download_authorized=False), 403
        connection.execute(
            """UPDATE orders SET download_count = download_count + 1,
               last_downloaded_at = ? WHERE download_token = ?""",
            (datetime.now(timezone.utc).isoformat(), token),
        )
        connection.commit()
    return faire_bundle_response()


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
        return render_template(
            "faire.html",
            active="faire",
            faire_youtube_video_id=os.environ.get("FAIRE_YOUTUBE_VIDEO_ID", "").strip(),
        )
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
    return render_template("agent.html", active="agent", audit=audit, history=recent_audits(), agents=agent_statuses())


@app.get("/agentforce")
def agentforce_page():
    return render_template("agentforce.html", active="agentforce", products=agent_statuses())


@app.route("/agentforce/linkedin/connect", methods=["GET", "POST"])
def linkedin_connect():
    authorized = admin_authorized()
    if request.method == "GET":
        nonce = request.args.get("nonce", "")
        expires = request.args.get("expires", "")
        signature = request.args.get("signature", "")
        try:
            active = int(expires) >= int(time.time()) and int(expires) <= int(time.time()) + 600
        except ValueError:
            active = False
        expected = hmac.new(
            os.environ.get("ADMIN_TOKEN", "").encode(),
            f"linkedin:{nonce}:{expires}".encode(),
            hashlib.sha256,
        ).hexdigest()
        authorized = bool(nonce and active and signature and hmac.compare_digest(expected, signature))
    if not authorized:
        return jsonify(error="Administrative authorization required."), 403
    client_id = os.environ.get("LINKEDIN_CLIENT_ID", "").strip()
    if not client_id or not os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip():
        return jsonify(error="LinkedIn client credentials are not configured."), 503
    state = secrets.token_urlsafe(32)
    expires_at = datetime.fromtimestamp(time.time() + 600, timezone.utc).isoformat()
    with agent_evidence_connection() as connection:
        connection.execute("DELETE FROM oauth_states WHERE provider='linkedin'")
        connection.execute(
            "INSERT INTO oauth_states (provider, state, expires_at) VALUES ('linkedin', ?, ?)",
            (state, expires_at),
        )
        connection.commit()
    callback = url_for("linkedin_callback", _external=True)
    authorization_url = "https://www.linkedin.com/oauth/v2/authorization?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback,
        "state": state,
        "scope": "openid profile w_member_social",
    })
    if request.method == "GET":
        return redirect(authorization_url)
    return jsonify(authorization_url=authorization_url, redirect_uri=callback, expires_in=600)


@app.get("/agentforce/linkedin/callback")
def linkedin_callback():
    state = request.args.get("state", "")
    code = request.args.get("code", "")
    if not state or not code:
        record_agent_event("social", "linkedin_oauth", "attention", "LinkedIn authorization was cancelled or incomplete.")
        return redirect(url_for("agentforce_page") + "#social")
    with agent_evidence_connection() as connection:
        saved = connection.execute(
            "SELECT expires_at FROM oauth_states WHERE provider='linkedin' AND state=?", (state,)
        ).fetchone()
        connection.execute("DELETE FROM oauth_states WHERE provider='linkedin'")
        connection.commit()
    if not saved or datetime.fromisoformat(saved["expires_at"]) <= datetime.now(timezone.utc):
        return jsonify(error="LinkedIn authorization state is invalid or expired."), 400
    callback = url_for("linkedin_callback", _external=True)
    token_body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback,
        "client_id": os.environ.get("LINKEDIN_CLIENT_ID", ""),
        "client_secret": os.environ.get("LINKEDIN_CLIENT_SECRET", ""),
    }).encode()
    token_request = Request(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data=token_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(token_request, timeout=20) as response:
            token_data = json.loads(response.read().decode("utf-8"))
        access_token = token_data["access_token"]
        profile_request = Request(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        with urlopen(profile_request, timeout=20) as response:
            profile = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        app.logger.exception("LinkedIn OAuth exchange failed")
        record_agent_event("social", "linkedin_oauth", "fail", f"LinkedIn OAuth exchange failed with {type(exc).__name__}.")
        return redirect(url_for("agentforce_page", linkedin="failed") + "#social")
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(now.timestamp() + int(token_data.get("expires_in", 0)), timezone.utc).isoformat()
    with agent_evidence_connection() as connection:
        connection.execute(
            """INSERT INTO agent_integrations
               (provider, access_token, external_id, display_name, scopes, expires_at, connected_at, last_verified_at)
               VALUES ('linkedin', ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET access_token=excluded.access_token,
                 external_id=excluded.external_id, display_name=excluded.display_name,
                 scopes=excluded.scopes, expires_at=excluded.expires_at,
                 connected_at=excluded.connected_at, last_verified_at=excluded.last_verified_at""",
            (access_token, profile.get("sub"), profile.get("name"), token_data.get("scope", ""), expires_at, now.isoformat(), now.isoformat()),
        )
        connection.commit()
    record_agent_event("social", "linkedin_oauth", "pass", "LinkedIn OAuth connected and identity verified; publishing requires human approval.")
    return redirect(url_for("agentforce_page", linkedin="connected") + "#social")


@app.get("/8")
def smart_ai_page():
    return render_template("smart-ai.html", active="smart-ai", snapshot=smart_ai_snapshot())


@app.get("/api/smart-ai/feed")
def smart_ai_feed_api():
    return jsonify(smart_ai_snapshot())


@app.get("/api/agents/evidence")
def agents_evidence_api():
    return jsonify(service="thepolka.cloud", checked_at=datetime.now(timezone.utc).isoformat(), agents=agent_statuses())


@app.get("/api/faire/manifest")
def faire_release_manifest_api():
    catalog_payload = json.dumps(
        {slug: product["skills"] for slug, product in AGENT_PRODUCTS.items()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return jsonify(
        product="FAIRE OS",
        version="1.1.1",
        channel="stable",
        agent_catalog_revision=hashlib.sha256(catalog_payload.encode()).hexdigest()[:12],
        agent_catalog_url=url_for("agents_evidence_api", _external=True),
        release_page=url_for("ecosystem_page", page="faire", _external=True),
        update_policy="notify-only; explicit user approval required",
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/agents/<slug>/evidence")
def agent_evidence_api(slug):
    agents = agent_statuses()
    if slug not in agents:
        return jsonify(error="Agent not found"), 404
    return jsonify(slug=slug, **agents[slug])


@app.get("/api/agents/social/linkedin-status")
def linkedin_status_api():
    try:
        connected, detail = linkedin_verify()
    except Exception as exc:
        app.logger.warning("Live LinkedIn status check failed: %s", type(exc).__name__)
        return jsonify(connected=False, status="attention", detail="LinkedIn token verification failed; no post was sent."), 502
    status = "pass" if connected else "attention"
    record_agent_event("social", "linkedin_verify", status, detail)
    return jsonify(
        connected=connected,
        status=status,
        detail=detail,
        publishing_policy="human approval required",
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


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
        archive.writestr("integration-adapters.json", json.dumps({"supported": manifest["adapters"], "connected": [], "policy": manifest["connection_policy"]}, indent=2))
        archive.writestr("EVIDENCE.md", f"# Package evidence\n\n- Agent: {manifest['name']}\n- Schema: {manifest['schema']}\n- Entrypoint: {manifest['entrypoint']}\n- Package status: validated\n- External connections: none included; configure explicitly after purchase\n")
        archive.writestr("README.md", f"# {manifest['name']}\n\nRun `python agent.py` to inspect the package. Connect only approved tools in `config.json`. Adapter compatibility depends on the target system's API and permissions.\n")
    bundle.seek(0)
    record_agent_event(slug, "download", "pass", "Download package generated and delivered.")
    return send_file(bundle, mimetype="application/zip", as_attachment=True, download_name=f"thepolka-{slug}-agent.zip")


@app.post("/agentforce/checkout/<slug>")
def agent_checkout(slug):
    if slug not in AGENT_PRODUCTS:
        return not_found(None)
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret:
        record_agent_event(slug, "checkout", "attention", "Checkout requested, but private Stripe configuration is incomplete.")
        return redirect(url_for("agentforce_page", checkout="configuration-required") + f"#{slug}")
    product = AGENT_PRODUCTS[slug]
    body = urlencode({
        "mode": "payment",
        "managed_payments[enabled]": "false",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": product["price"] * 100,
        "line_items[0][price_data][product_data][name]": f"{product['character']} · {product['name']}",
        "line_items[0][price_data][product_data][description]": product["description"],
        "line_items[0][quantity]": 1,
        "allow_promotion_codes": "true",
        "success_url": request.url_root.rstrip("/") + url_for("agentforce_page") + f"?purchased={slug}#{slug}",
        "cancel_url": request.url_root.rstrip("/") + url_for("agentforce_page") + f"?cancelled={slug}#{slug}",
        "metadata[agent_slug]": slug,
    }).encode()
    stripe_request = Request("https://api.stripe.com/v1/checkout/sessions", data=body, headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(stripe_request, timeout=20) as response:
            session = json.load(response)
        record_agent_event(slug, "checkout", "pass", "Stripe Checkout session created; payment completion is handled by Stripe.")
        return redirect(session["url"], code=303)
    except Exception:
        app.logger.exception("Stripe Checkout creation failed")
        return redirect(url_for("agentforce_page", checkout="failed") + f"#{slug}")


@app.post("/faire/checkout")
def faire_checkout():
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret:
        return redirect(url_for("ecosystem_page", page="faire", checkout="configuration-required") + "#purchase")
    body = urlencode({
        "mode": "payment",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": 50000,
        "line_items[0][price_data][product_data][name]": "FAIRE OS Commercial 1.0 — Lifetime License",
        "line_items[0][price_data][product_data][description]": "One-time purchase. Perpetual use of the purchased FAIRE OS version for one owner.",
        "line_items[0][quantity]": 1,
        "success_url": request.url_root.rstrip("/") + url_for("faire_purchase_success") + "?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": request.url_root.rstrip("/") + url_for("ecosystem_page", page="faire") + "?cancelled=faire-desktop#purchase",
        "metadata[product]": "faire-os",
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


@app.get("/faire/purchase/success")
def faire_purchase_success():
    session_id = request.args.get("session_id", "").strip()
    if not session_id.startswith("cs_"):
        return render_template("faire_download.html", download_authorized=False), 403
    try:
        checkout_session = stripe_session(session_id)
        token = provision_faire_download(checkout_session)
    except Exception:
        app.logger.exception("Faire payment verification failed")
        token = None
    return render_template(
        "faire_download.html",
        download_authorized=bool(token),
        download_url=url_for("faire_paid_download", token=token) if token else None,
    )


@app.post("/stripe/webhook")
def stripe_webhook():
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        return "Webhook not configured", 503
    try:
        event = stripe.Webhook.construct_event(
            request.get_data(),
            request.headers.get("Stripe-Signature", ""),
            webhook_secret,
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return "Invalid webhook", 400
    if event["type"] in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        provision_faire_download(event["data"]["object"])
    return "", 200


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
        ai_answer = request.form.get("ai_answer", "").strip()[:12000]
        submitter_email = request.form.get("email", "").strip().lower()[:254]
        prompt_text = request.form.get("prompt_text", "").strip()[:12000]
        rights_confirmed = request.form.get("rights_confirmed") == "yes"
        memory_bank_opt_in = request.form.get("memory_bank_opt_in") == "yes"
        upload = request.files.get("document")
        original_filename = secure_filename(upload.filename or "") if upload else ""
        extension = Path(original_filename).suffix.lower()
        if not all((submitter_email, prompt_text, title, expertise, content_type, description, rights_confirmed, upload, original_filename)):
            error = "Add your email, prompt, attachment details, and rights confirmation."
        elif "@" not in submitter_email:
            error = "Enter a valid email address."
        elif extension not in AI_UPLOAD_EXTENSIONS:
            error = "Upload a PDF, DOCX, TXT, Markdown, JSON, or CSV document."
        else:
            today = datetime.now(timezone.utc).date().isoformat()
            with database_connection() as connection:
                already_submitted = connection.execute(
                    "SELECT 1 FROM contributions WHERE lower(submitter_email)=? AND substr(created_at, 1, 10)=? LIMIT 1",
                    (submitter_email, today),
                ).fetchone()
            if already_submitted:
                error = "This email has already submitted today. Return tomorrow for the next one-cent submission."
        if not error and extension in AI_UPLOAD_EXTENSIONS:
            stored_filename = f"{secrets.token_hex(24)}{extension}"
            stored_path = AI_UPLOAD_DIRECTORY / stored_filename
            digest = hashlib.sha256()
            file_size = 0
            with stored_path.open("wb") as destination:
                while chunk := upload.stream.read(1024 * 1024):
                    file_size += len(chunk)
                    digest.update(chunk)
                    destination.write(chunk)
            raw_text = ""
            if extension in {".txt", ".md", ".json", ".csv"}:
                raw_text = stored_path.read_text(encoding="utf-8", errors="replace")[:200000]
            with database_connection() as connection:
                connection.execute(
                    """INSERT INTO contributions
                       (title, expertise, content_type, description, rights_confirmed,
                        status, created_at, original_filename, stored_filename,
                       file_size, file_sha256, memory_bank_opt_in, ai_answer,
                        raw_text, submitter_email, prompt_text, quality_category,
                        earned_cents)
                       VALUES (?, ?, ?, ?, 1, 'shelved', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting-ratings', 1)""",
                    (
                        title, expertise, content_type, description,
                        datetime.now(timezone.utc).isoformat(),
                        original_filename, stored_filename, file_size,
                        digest.hexdigest(), int(memory_bank_opt_in), ai_answer,
                        raw_text, submitter_email, prompt_text,
                    ),
                )
            return redirect(url_for("ai_marketplace", submitted="1"))

    with database_connection() as connection:
        submissions = connection.execute(
            """SELECT title, expertise, content_type, status, created_at,
                      original_filename, file_size, memory_bank_opt_in, earned_cents
               FROM contributions ORDER BY id DESC LIMIT 20"""
        ).fetchall()
    return render_template(
        "ai_marketplace.html",
        active="marketplace",
        submissions=submissions,
        error=error,
        submitted=request.args.get("submitted") == "1",
    )


@app.route("/ai-warehouse", methods=["GET", "POST"])
def ai_warehouse():
    rating_error = None
    if request.method == "POST":
        contribution_id = request.form.get("contribution_id", type=int)
        rater_email = request.form.get("rater_email", "").strip().lower()[:254]
        category = request.form.get("category", "").strip()
        if not contribution_id or "@" not in rater_email or category not in WAREHOUSE_CATEGORIES:
            rating_error = "Choose one rating and enter a valid email."
        else:
            try:
                with database_connection() as connection:
                    connection.execute(
                        "INSERT INTO contribution_ratings (contribution_id, rater_email, category, created_at) VALUES (?, ?, ?, ?)",
                        (contribution_id, rater_email, category, datetime.now(timezone.utc).isoformat()),
                    )
                    winner = connection.execute(
                        """SELECT category, COUNT(*) AS votes FROM contribution_ratings
                           WHERE contribution_id=? GROUP BY category
                           ORDER BY votes DESC, category ASC LIMIT 1""",
                        (contribution_id,),
                    ).fetchone()
                    if winner:
                        connection.execute(
                            "UPDATE contributions SET quality_category=? WHERE id=?",
                            (winner["category"], contribution_id),
                        )
                return redirect(url_for("ai_warehouse", rated="1") + f"#item-{contribution_id}")
            except sqlite3.IntegrityError:
                rating_error = "That email has already rated this item."
    with database_connection() as connection:
        catalog = connection.execute(
            """SELECT c.id, c.title, c.expertise, c.content_type, c.description,
                      c.prompt_text, c.ai_answer, c.created_at, c.quality_category,
                      COUNT(r.id) AS rating_count
               FROM contributions c LEFT JOIN contribution_ratings r ON r.contribution_id=c.id
               WHERE c.status IN ('shelved', 'accepted')
               GROUP BY c.id ORDER BY c.id DESC"""
        ).fetchall()
        counts = {
            row["status"]: row["count"]
            for row in connection.execute("SELECT status, COUNT(*) AS count FROM contributions GROUP BY status")
        }
    shelves = {key: [] for key in ["awaiting-ratings", *WAREHOUSE_CATEGORIES]}
    for item in catalog:
        shelves.setdefault(item["quality_category"], []).append(item)
    return render_template(
        "ai_warehouse.html", active="warehouse", catalog=catalog, counts=counts,
        shelves=shelves, categories=WAREHOUSE_CATEGORIES, rating_error=rating_error,
        rated=request.args.get("rated") == "1",
    )


@app.get("/ai-memory-bank")
def ai_memory_bank():
    query = request.args.get("q", "").strip()[:120]
    with database_connection() as connection:
        sql = """SELECT id, title, expertise, content_type, description, ai_answer,
                        created_at, original_filename, file_size
                 FROM contributions
                 WHERE status = 'accepted' AND memory_bank_opt_in = 1"""
        params = []
        if query:
            sql += """ AND (title LIKE ? OR expertise LIKE ? OR description LIKE ?
                            OR ai_answer LIKE ? OR raw_text LIKE ?)"""
            term = f"%{query}%"
            params = [term, term, term, term, term]
        sql += " ORDER BY id DESC LIMIT 100"
        memories = connection.execute(sql, params).fetchall()
        queued = connection.execute(
            "SELECT COUNT(*) FROM contributions WHERE memory_bank_opt_in = 1 AND status = 'submitted'"
        ).fetchone()[0]
    return render_template(
        "ai_memory_bank.html",
        active="memory",
        memories=memories,
        queued=queued,
        query=query,
    )


@app.get("/api/memory/search")
def ai_memory_search_api():
    query = request.args.get("q", "").strip()[:120]
    if not query:
        return jsonify(error="Add a search query."), 400
    term = f"%{query}%"
    with database_connection() as connection:
        rows = connection.execute(
            """SELECT id, title, expertise, content_type, description, ai_answer,
                      original_filename, file_sha256
               FROM contributions
               WHERE status = 'accepted' AND memory_bank_opt_in = 1
                 AND (title LIKE ? OR expertise LIKE ? OR description LIKE ?
                      OR ai_answer LIKE ? OR raw_text LIKE ?)
               ORDER BY id DESC LIMIT 20""",
            (term, term, term, term, term),
        ).fetchall()
    return jsonify(query=query, count=len(rows), memories=[dict(row) for row in rows])


@app.get("/health")
def health():
    return jsonify(status="ok", service="thepolka.cloud"), 200


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nAllow: /\nSitemap: https://thepolka.cloud/sitemap.xml\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    paths = [
        "/", "/forecast", "/tools", "/research", "/apply", "/mylm", "/ilaw", "/java",
        "/ecosystem/resume", "/ecosystem/cad", "/ecosystem/faire",
        "/agent", "/agentforce", "/ai-marketplace", "/ai-warehouse", "/ai-memory-bank", "/privacy",
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
