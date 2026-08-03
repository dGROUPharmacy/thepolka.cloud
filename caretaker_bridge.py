"""Read-only local Caretaker bridge for ThePolka.Cloud."""

import argparse
import hashlib
import hmac
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_CONFIG = Path(__file__).resolve().parent / "instance" / "caretaker.local.json"


def load_config(path):
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    required = ("endpoint", "bridge_id", "secret", "roots", "agent_trash")
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


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def defender_status():
    if os.name != "nt":
        return {"available": False, "realtime_enabled": False, "signature_age_days": -1, "quick_scan_age_days": -1}
    command = (
        "$s=Get-MpComputerStatus; "
        "@{available=$s.AntivirusEnabled;realtime_enabled=$s.RealTimeProtectionEnabled;"
        "signature_age_days=$s.AntivirusSignatureAge;quick_scan_age_days=$s.QuickScanAge} | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=20, check=True,
        )
        status = json.loads(completed.stdout)
        if status.get("available") is None or status.get("realtime_enabled") is None:
            raise ValueError("Defender status unavailable")
        return status
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return {"available": False, "realtime_enabled": False, "signature_age_days": -1, "quick_scan_age_days": -1}


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
        "duplicate_groups": 0,
        "duplicate_files": 0,
        "duplicate_reclaimable_bytes": 0,
        "archives_checked": 0,
        "corrupt_archives": 0,
    }
    stale_before = time.time() - (30 * 86400)
    database_paths = []
    archive_paths = []
    files_by_size = defaultdict(list)
    duplicate_candidates = []
    for root in roots:
        for current, directories, files in os.walk(root, followlinks=False):
            directories[:] = [name for name in directories if name not in {".git", ".venv", "venv", "node_modules", "Agent Trash"}]
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
                if stat.st_size > 0:
                    files_by_size[stat.st_size].append(path)
                totals["large_files"] += int(stat.st_size >= 100 * 1024 * 1024)
                totals["stale_files"] += int(stat.st_mtime < stale_before)
                if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"} and len(database_paths) < 50:
                    database_paths.append(path)
                if path.suffix.lower() == ".zip" and stat.st_size <= 500 * 1024 * 1024 and len(archive_paths) < 100:
                    archive_paths.append(path)
    for path in database_paths:
        totals["databases_checked"] += 1
        try:
            healthy = database_quick_check(path)
        except (OSError, sqlite3.Error):
            healthy = False
        totals["database_failures"] += int(not healthy)
    for path in archive_paths:
        totals["archives_checked"] += 1
        try:
            with zipfile.ZipFile(path) as archive:
                corrupt = archive.testzip() is not None
        except (OSError, zipfile.BadZipFile):
            corrupt = True
        totals["corrupt_archives"] += int(corrupt)
    for size, candidates in files_by_size.items():
        if len(candidates) < 2:
            continue
        hashes = defaultdict(list)
        for path in candidates:
            try:
                hashes[file_sha256(path)].append(path)
            except OSError:
                totals["scan_errors"] += 1
        for digest, paths in hashes.items():
            count = len(paths)
            if count > 1:
                totals["duplicate_groups"] += 1
                totals["duplicate_files"] += count
                totals["duplicate_reclaimable_bytes"] += size * (count - 1)
                ordered = sorted(paths, key=lambda item: str(item).lower())
                for path in ordered[1:]:
                    duplicate_candidates.append({
                        "id": hashlib.sha256(str(path).encode()).hexdigest()[:16],
                        "path": str(path),
                        "size": size,
                        "sha256": digest,
                        "suggested_keep": str(ordered[0]),
                        "approved": False,
                    })
    disk = shutil.disk_usage(roots[0].anchor)
    totals["disk_free_bytes"] = disk.free
    totals["disk_free_percent"] = round((disk.free / disk.total) * 100, 1) if disk.total else 0
    totals["cpu_count"] = os.cpu_count() or 1
    totals["defender"] = defender_status()
    totals["_duplicate_candidates"] = duplicate_candidates
    return totals


def write_review_manifest(config, candidates):
    trash = Path(config["agent_trash"]).expanduser().resolve()
    trash.mkdir(parents=True, exist_ok=True)
    manifest_path = trash / "duplicate-review.json"
    existing_approvals = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            existing_approvals = {item["id"]: bool(item.get("approved")) for item in previous.get("items", [])}
        except (OSError, json.JSONDecodeError, KeyError):
            existing_approvals = {}
    for item in candidates:
        item["approved"] = existing_approvals.get(item["id"], False)
    payload = {
        "policy": "Review each item. Set approved=true only for files Caretaker may MOVE. Nothing is ever deleted.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent_trash": str(trash),
        "items": candidates,
    }
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(manifest_path)
    return manifest_path


def path_within(path, roots):
    return any(path == root or root in path.parents for root in roots)


def stage_approved_files(config):
    roots = config["roots"]
    trash = Path(config["agent_trash"]).expanduser().resolve()
    manifest_path = trash / "duplicate-review.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch = trash / datetime.now().strftime("review-%Y%m%d-%H%M%S")
    moved = []
    for item in manifest.get("items", []):
        if not item.get("approved"):
            continue
        source = Path(item["path"]).resolve(strict=True)
        if not source.is_file() or not path_within(source, roots) or trash in source.parents:
            raise ValueError(f"Refusing out-of-scope move: {source}")
        root = next(root for root in roots if source == root or root in source.parents)
        destination = batch / root.name / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination = destination.with_name(f"{destination.stem}-{item['id']}{destination.suffix}")
        shutil.move(str(source), str(destination))
        moved.append({"id": item["id"], "from": str(source), "to": str(destination), "moved_at": datetime.now(timezone.utc).isoformat()})
    if moved:
        log_path = trash / "move-log.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            for entry in moved:
                handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
    return moved


def check_in(config):
    report = scan_roots(config["roots"])
    duplicate_candidates = report.pop("_duplicate_candidates", [])
    manifest_path = write_review_manifest(config, duplicate_candidates)
    report.update({
        "machine_name": platform.node() or "Windows workstation",
        "roots": [root.name for root in config["roots"]],
        "read_only": True,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "move_candidates": len(duplicate_candidates),
        "review_manifest_ready": manifest_path.exists(),
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
    parser.add_argument("--stage-approved", action="store_true", help="Move only manifest entries explicitly marked approved=true")
    args = parser.parse_args()
    config = load_config(args.config.resolve())
    if args.stage_approved:
        print(json.dumps({"moved": stage_approved_files(config), "deleted": 0}, indent=2))
        return
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
