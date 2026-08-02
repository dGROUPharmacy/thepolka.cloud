"""Read-only local Caretaker bridge for ThePolka.Cloud."""

import argparse
import hashlib
import hmac
import json
import os
import platform
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_CONFIG = Path(__file__).resolve().parent / "instance" / "caretaker.local.json"


def load_config(path):
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    required = ("endpoint", "bridge_id", "secret", "roots")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"Missing configuration: {', '.join(missing)}")
    roots = [Path(item).expanduser().resolve(strict=True) for item in config["roots"]]
    if not all(root.is_dir() for root in roots):
        raise ValueError("Every approved Caretaker root must be a directory")
    config["roots"] = roots
    return config


def database_quick_check(path):
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as connection:
        return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def scan_roots(roots):
    totals = {
        "files": 0,
        "directories": 0,
        "bytes": 0,
        "large_files": 0,
        "stale_files": 0,
        "databases_checked": 0,
        "database_failures": 0,
        "scan_errors": 0,
    }
    stale_before = time.time() - (30 * 86400)
    database_paths = []
    for root in roots:
        for current, directories, files in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if name not in {".git", ".venv", "venv", "node_modules"}]
            totals["directories"] += len(directories)
            for name in files:
                totals["files"] += 1
                path = Path(current) / name
                try:
                    stat = path.stat()
                except OSError:
                    totals["scan_errors"] += 1
                    continue
                totals["bytes"] += stat.st_size
                totals["large_files"] += int(stat.st_size >= 100 * 1024 * 1024)
                totals["stale_files"] += int(stat.st_mtime < stale_before)
                if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"} and len(database_paths) < 50:
                    database_paths.append(path)
    for path in database_paths:
        totals["databases_checked"] += 1
        try:
            healthy = database_quick_check(path)
        except (OSError, sqlite3.Error):
            healthy = False
        totals["database_failures"] += int(not healthy)
    return totals


def check_in(config):
    report = scan_roots(config["roots"])
    report.update({
        "machine_name": platform.node() or "Windows workstation",
        "roots": [root.name for root in config["roots"]],
        "read_only": True,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    })
    body = json.dumps(report, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(config["secret"].encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    request = Request(
        config["endpoint"],
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Caretaker-Bridge": config["bridge_id"],
            "X-Caretaker-Timestamp": timestamp,
            "X-Caretaker-Signature": signature,
        },
    )
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    print(json.dumps({"local_report": report, "cloud_response": result}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="Run the read-only ThePolka.Cloud Caretaker bridge")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config.resolve())
    interval = max(60, int(config.get("interval_seconds", 300)))
    while True:
        try:
            check_in(config)
        except Exception as exc:
            print(json.dumps({"status": "error", "error": type(exc).__name__, "at": datetime.now(timezone.utc).isoformat()}))
            if args.once:
                raise
        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
