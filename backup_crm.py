#!/usr/bin/env python3
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path


BASE_URL = "https://lead-crm-tommaso.fly.dev"
LOGIN_URL = f"{BASE_URL}/api/login"
SESSION_URL = f"{BASE_URL}/api/session"
EXPORT_URL = f"{BASE_URL}/api/export/leads.csv"
BACKUP_DIR = Path.home() / "crm-backups"
BACKUP_PREFIX = "crm-backup-"
BACKUP_SUFFIX = ".csv"
RETENTION_DAYS = 30
EXPECTED_HEADERS = [
    "id",
    "company_name",
    "sector",
    "city",
    "website",
    "category",
    "stage",
    "priority",
    "score",
    "opportunity",
    "notes",
    "next_follow_up",
    "created_at",
]


def fail(message, exit_code=1):
    print(f"ERRORE: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def get_required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        fail(f"La variabile d'ambiente {name} non e impostata.")
    return value


def build_opener():
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def post_json(opener, url, payload):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "leadcrm-backup/1.0",
        },
        method="POST",
    )
    with opener.open(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return response.status, body, dict(response.headers.items())


def get_json(opener, url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "leadcrm-backup/1.0",
        },
        method="GET",
    )
    with opener.open(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)


def get_text(opener, url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
            "User-Agent": "leadcrm-backup/1.0",
        },
        method="GET",
    )
    with opener.open(request, timeout=60) as response:
        body = response.read().decode("utf-8")
        return response.status, body, response.headers.get("Content-Type", "")


def login(opener, email, password):
    try:
        status, body, headers = post_json(
            opener,
            LOGIN_URL,
            {"email": email, "password": password},
        )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        fail(f"Login fallito con HTTP {exc.code}: {error_body}")
    except urllib.error.URLError as exc:
        fail(f"Login fallito: {exc.reason}")

    if status != 200:
        fail(f"Login fallito con status inatteso: {status}")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        fail("Login fallito: risposta JSON non valida.")

    if "Set-Cookie" not in headers:
        fail("Login fallito: cookie di sessione non ricevuto.")
    if not payload.get("user"):
        fail("Login fallito: utente non presente nella risposta.")


def verify_session(opener):
    try:
        status, payload = get_json(opener, SESSION_URL)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        fail(f"Verifica sessione fallita con HTTP {exc.code}: {error_body}")
    except urllib.error.URLError as exc:
        fail(f"Verifica sessione fallita: {exc.reason}")

    if status != 200 or not payload.get("user"):
        fail("Sessione non valida dopo il login.")


def download_export(opener):
    try:
        status, csv_text, content_type = get_text(opener, EXPORT_URL)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        fail(f"Download export fallito con HTTP {exc.code}: {error_body}")
    except urllib.error.URLError as exc:
        fail(f"Download export fallito: {exc.reason}")

    if status != 200:
        fail(f"Download export fallito con status inatteso: {status}")
    if "text/csv" not in content_type.lower():
        fail(f"Content-Type inatteso per export CSV: {content_type or 'vuoto'}")
    if not csv_text.strip():
        fail("Export CSV vuoto.")

    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        fail("Export CSV senza intestazione.")
    if header != EXPECTED_HEADERS:
        fail(f"Intestazione CSV inattesa: {header}")

    return csv_text


def save_backup(csv_text):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    destination = BACKUP_DIR / f"{BACKUP_PREFIX}{timestamp}{BACKUP_SUFFIX}"
    destination.write_text(csv_text, encoding="utf-8", newline="")
    return destination


def cleanup_old_backups():
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed = []
    if not BACKUP_DIR.exists():
        return removed
    for path in BACKUP_DIR.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"):
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def main():
    email = get_required_env("CRM_BACKUP_EMAIL")
    password = get_required_env("CRM_BACKUP_PASSWORD")
    opener = build_opener()
    login(opener, email, password)
    verify_session(opener)
    csv_text = download_export(opener)
    backup_path = save_backup(csv_text)
    removed = cleanup_old_backups()
    print(
        f"Backup completato con successo: {backup_path} "
        f"(rimossi {len(removed)} backup piu vecchi di {RETENTION_DAYS} giorni)."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        fail("Backup interrotto manualmente.", exit_code=130)
