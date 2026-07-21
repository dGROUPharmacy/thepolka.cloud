"""Production entry point for ThePolka.Cloud."""

import os
from pathlib import Path

from flask import Flask, jsonify, render_template
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


@app.get("/")
def home():
    return render_template("index.html", active="home")


@app.get("/health")
def health():
    return jsonify(status="ok", service="thepolka.cloud"), 200


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
