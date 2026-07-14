#!/usr/bin/env python3
import argparse
import base64
import binascii
import csv
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.environ.get("CRM_DATA_DIR", "").strip()).expanduser() if os.environ.get("CRM_DATA_DIR", "").strip() else APP_DIR / "data"
EXPORT_DIR = APP_DIR / "exports"
DB_PATH = DATA_DIR / "crm.sqlite3"
SESSION_COOKIE = "leadcrm_session"
SESSION_TTL_SECONDS = 14 * 24 * 60 * 60
PASSWORD_ITERATIONS = 260000
ROLES = ["super_admin", "admin", "member"]
ROLE_LABELS = {
    "super_admin": "Super admin",
    "admin": "Admin",
    "member": "Operatore",
}
BOOTSTRAP_SUPER_ADMIN = {
    "email": "t.v.webspecialist@gmail.com",
    "name": "Tommaso",
    "password_hash": "pbkdf2_sha256$260000$Bh0kJPGZOiKXSeXDIc8xXw$vWmyg0NrGTBzslGVxdF7qARVWwss9zaAAXkkgd0HzXU",
}

STAGES = [
    "Nuovo",
    "Da arricchire",
    "Pronto da contattare",
    "Da verificare",
    "Contattato",
    "Interessato",
    "Preventivo",
    "Vinto",
    "Chiuso",
    "Perso",
]

CATEGORIES = [
    "Da qualificare",
    "Da arricchire",
    "Nessun sito",
    "Sito critico",
    "Sito migliorabile",
    "Presenza social debole",
    "Presenza discreta",
]

PRIORITIES = ["Alta", "Media", "Bassa"]
CONTACT_TYPES = ["email", "telefono", "whatsapp", "instagram", "facebook", "linkedin", "tiktok", "sito", "altro"]
SETTING_KEYS = {
    "google_places_enabled",
    "google_places_api_key",
    "anthropic_api_key",
    "anthropic_model",
    "ai_provider",
    "openai_api_key",
    "openai_model",
    "monthly_budget_eur",
    "target_zones",
    "target_sectors",
    "places_default_limit",
    "places_require_contact",
    "places_only_without_website",
    "openai_price_floor",
    "openai_price_ceiling",
    "ai_seller_name",
    "ai_business_name",
    "ai_tone",
    "ai_services",
    "ai_ideal_customer",
    "ai_offer_focus",
    "ai_proof_points",
    "ai_message_style",
    "ai_followup_plan",
    "assistant_knowledge",
}
DEFAULT_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
DEFAULT_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
AI_PROVIDERS = {"auto", "anthropic", "openai"}
OVERPASS_ENDPOINTS = [url.strip() for url in os.environ.get("CRM_OVERPASS_URLS", "").split(",") if url.strip()] or [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
ANTHROPIC_MODEL_OPTIONS = [
    {
        "id": "claude-sonnet-5",
        "label": "Claude Sonnet 5",
        "summary": "Miglior equilibrio tra intelligenza, velocita e costo per il CRM.",
    },
    {
        "id": "claude-opus-4-8",
        "label": "Claude Opus 4.8",
        "summary": "Piu capace per analisi complesse, reasoning e compiti piu pesanti.",
    },
    {
        "id": "claude-haiku-4-5",
        "label": "Claude Haiku 4.5",
        "summary": "Piu veloce ed economico per alti volumi e bassa latenza.",
    },
    {
        "id": "claude-fable-5",
        "label": "Claude Fable 5",
        "summary": "Massima capacita disponibile per ragionamento avanzato e lavoro agentico.",
    },
]
PUBLIC_APP_URL = os.environ.get("CRM_PUBLIC_BASE_URL", "https://lead-crm-tommaso.fly.dev").strip() or "https://lead-crm-tommaso.fly.dev"
PUBLIC_APP_NAME = os.environ.get("CRM_PUBLIC_APP_NAME", "lead-crm-tommaso").strip() or "lead-crm-tommaso"
PRIMARY_REGION = os.environ.get("CRM_PRIMARY_REGION", "fra").strip() or "fra"
FACUNDO_NAME = "Facundo"
FACUNDO_ACTION_TYPES = [
    "open_lead",
    "search_leads",
    "create_lead",
    "update_lead",
    "create_reminder",
    "generate_message",
    "research_lead",
    "score_lead",
]
FACUNDO_STAGE_ALIASES = {
    "nuovo": "Nuovo",
    "da arricchire": "Da arricchire",
    "pronto da contattare": "Pronto da contattare",
    "da verificare": "Da verificare",
    "contattato": "Contattato",
    "interessato": "Interessato",
    "preventivo": "Preventivo",
    "vinto": "Vinto",
    "chiuso": "Chiuso",
    "perso": "Perso",
}
FACUNDO_PRIORITY_ALIASES = {"alta": "Alta", "media": "Media", "bassa": "Bassa"}
DEFAULT_TARGET_ZONES = ["Milano", "Brescia", "Verona", "Vicenza", "Padova"]
DEFAULT_TARGET_SECTORS = [
    "restaurants",
    "hairdressers",
    "beauty",
    "dentists",
    "gyms",
    "hotels",
    "car_repair",
    "estate_agents",
]
DISCOVERY_SECTORS = [
    {"key": "restaurants", "label": "Ristoranti / bar"},
    {"key": "hairdressers", "label": "Parrucchieri"},
    {"key": "beauty", "label": "Estetisti / beauty"},
    {"key": "dentists", "label": "Dentisti"},
    {"key": "gyms", "label": "Palestre"},
    {"key": "hotels", "label": "Hotel / B&B"},
    {"key": "shops", "label": "Negozi"},
    {"key": "car_repair", "label": "Officine / auto"},
    {"key": "lawyers", "label": "Avvocati"},
    {"key": "accountants", "label": "Commercialisti"},
    {"key": "estate_agents", "label": "Agenzie immobiliari"},
    {"key": "plumbers", "label": "Idraulici"},
    {"key": "electricians", "label": "Elettricisti"},
]

OSM_SECTOR_QUERIES = {
    "restaurants": [("amenity", ["restaurant", "cafe", "bar", "pub", "fast_food", "ice_cream"])],
    "hairdressers": [("shop", ["hairdresser"])],
    "beauty": [("shop", ["beauty", "massage", "cosmetics"])],
    "dentists": [("amenity", ["dentist"])],
    "gyms": [("leisure", ["fitness_centre"]), ("amenity", ["gym"])],
    "hotels": [("tourism", ["hotel", "guest_house", "bed_and_breakfast", "apartment"])],
    "shops": [("shop", None)],
    "car_repair": [("shop", ["car_repair", "car", "tyres"]), ("craft", ["auto_repair"])],
    "lawyers": [("office", ["lawyer"])],
    "accountants": [("office", ["accountant", "tax_advisor"])],
    "estate_agents": [("office", ["estate_agent"])],
    "plumbers": [("craft", ["plumber"])],
    "electricians": [("craft", ["electrician"])],
}

GOOGLE_SECTOR_TYPES = {
    "restaurants": "restaurant",
    "hairdressers": "hair_care",
    "beauty": "beauty_salon",
    "dentists": "dentist",
    "gyms": "gym",
    "hotels": "lodging",
    "shops": "store",
    "car_repair": "car_repair",
    "lawyers": "lawyer",
    "accountants": "accounting",
    "estate_agents": "real_estate_agency",
    "plumbers": "plumber",
    "electricians": "electrician",
}

SECTOR_PLAYBOOK = {
    "restaurants": {"weight": 8, "offer": "Sito menu e prenotazioni", "reason": "molte ricerche locali arrivano da mobile"},
    "hairdressers": {"weight": 6, "offer": "Sito vetrina + WhatsApp", "reason": "contatto rapido e immagini aumentano fiducia"},
    "beauty": {"weight": 7, "offer": "Sito servizi + Instagram", "reason": "immagini e offerte aiutano la scelta"},
    "dentists": {"weight": 10, "offer": "Sito fiducia + SEO locale", "reason": "settore ad alto valore per richiesta"},
    "gyms": {"weight": 7, "offer": "Landing iscrizioni", "reason": "promozioni e prova gratuita convertono bene"},
    "hotels": {"weight": 9, "offer": "Sito camere + richiesta diretta", "reason": "prenotazioni dirette riducono dipendenza da portali"},
    "shops": {"weight": 5, "offer": "Mini sito catalogo", "reason": "utile per orari, prodotti e mappa"},
    "car_repair": {"weight": 8, "offer": "Sito servizi + emergenze", "reason": "il bisogno e spesso immediato"},
    "lawyers": {"weight": 9, "offer": "Sito professionale + reputazione", "reason": "fiducia e specializzazioni contano molto"},
    "accountants": {"weight": 8, "offer": "Sito servizi + lead form", "reason": "servizi ricorrenti e valore cliente alto"},
    "estate_agents": {"weight": 9, "offer": "Sito immobiliare leggero", "reason": "foto, immobili e contatto rapido sono decisivi"},
    "plumbers": {"weight": 8, "offer": "Pagina emergenze locali", "reason": "ricerche urgenti ad alta intenzione"},
    "electricians": {"weight": 8, "offer": "Pagina servizi locali", "reason": "contatto rapido e copertura zona vendono"},
}

GOOGLE_DATA_FIELDS = [
    "azienda",
    "settore",
    "zona",
    "indirizzo",
    "telefono",
    "sito",
    "link Google Maps",
    "rating e recensioni",
    "stato attivita",
    "categoria CRM",
    "score opportunita",
    "problemi rilevati",
    "fonte e ID sorgente",
]

DUPLICATE_POLICY = [
    "stesso ID Google Places o OpenStreetMap",
    "stesso nome azienda nella stessa zona",
    "stesso telefono, email o profilo social gia salvato",
    "stessa fonte pubblica nel campo sorgente",
]

SCORE_RULES = [
    "sito assente: +35 punti",
    "telefono, WhatsApp o email presente: +18 punti",
    "settore con valore commerciale alto: +5/+10 punti",
    "poche recensioni o reputazione migliorabile: +4/+10 punti",
    "sito lento, non mobile o non HTTPS: +6/+18 punti",
    "lead gia avanzato o perso: penalita per evitare sprechi",
]

OPENAI_TASKS = [
    "analisi lead",
    "proposta commerciale",
    "messaggio personalizzato",
    "obiezioni probabili",
    "prezzo consigliato",
]

OPENAI_OUTPUTS = [
    "score e priorita",
    "perche il lead e interessante",
    "problemi da usare nell'audit",
    "pacchetto consigliato",
    "messaggio email o DM",
    "risposte alle obiezioni",
    "range prezzo coerente",
]

OPENAI_GUARDRAILS = [
    "non inventare contatti o informazioni non presenti",
    "usare tono rispettoso e non aggressivo",
    "preferire contatti mirati, non invii massivi",
    "segnalare quando i dati vanno verificati",
    "rispettare opt-out e consenso prima di campagne ripetute",
]

DEFAULT_AI_CONTROL = {
    "ai_seller_name": "Tommaso",
    "ai_business_name": "Studio digitale locale",
    "ai_tone": "concreto, educato, diretto",
    "ai_services": "\n".join(
        [
            "Sito one-page",
            "Restyling sito",
            "Google Business Profile",
            "Starter Instagram",
            "SEO locale base",
            "Manutenzione mensile",
        ]
    ),
    "ai_ideal_customer": "Attivita locali contattabili, con presenza online assente o migliorabile e bisogno chiaro di richieste da mobile.",
    "ai_offer_focus": "Mini sito locale veloce con contatti rapidi, WhatsApp, mappa, servizi e base SEO.",
    "ai_proof_points": "\n".join(
        [
            "prezzo leggero e chiaro",
            "tempi rapidi",
            "design mobile-first",
            "contatti e CTA piu visibili",
            "nessun vincolo lungo",
        ]
    ),
    "ai_message_style": "breve, personale, zero pressione",
    "ai_followup_plan": "\n".join(
        [
            "giorno 0: primo contatto",
            "giorno 3: follow-up breve",
            "giorno 7: seconda angolazione",
            "giorno 30: riattivazione leggera",
        ]
    ),
}

ASSISTANT_STOPWORDS = {
    "che",
    "con",
    "come",
    "della",
    "delle",
    "dello",
    "degli",
    "dalla",
    "dalle",
    "dallo",
    "dentro",
    "dopo",
    "fare",
    "fatto",
    "fino",
    "lead",
    "info",
    "sono",
    "sulla",
    "sulle",
    "sugli",
    "sugli",
    "suggerisci",
    "tutto",
    "questa",
    "questo",
    "quale",
    "quali",
    "dove",
    "quando",
    "perche",
    "quindi",
    "anche",
    "della",
    "degli",
}


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    sector TEXT,
    city TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    website TEXT,
    google_maps_url TEXT,
    source TEXT,
    category TEXT DEFAULT 'Da qualificare',
    stage TEXT DEFAULT 'Nuovo',
    priority TEXT DEFAULT 'Media',
    score INTEGER DEFAULT 0,
    opportunity TEXT,
    pain_points TEXT,
    notes TEXT,
    last_contacted_at TEXT,
    next_follow_up TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    value TEXT NOT NULL,
    label TEXT,
    is_primary INTEGER DEFAULT 0,
    consent_status TEXT DEFAULT 'Da verificare',
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    assigned_user_id INTEGER,
    kind TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    channel TEXT,
    outcome TEXT,
    due_at TEXT,
    notify_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS website_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    url TEXT NOT NULL,
    final_url TEXT,
    status_code INTEGER,
    title TEXT,
    meta_description TEXT,
    has_https INTEGER DEFAULT 0,
    has_viewport INTEGER DEFAULT 0,
    has_robots INTEGER DEFAULT 0,
    has_sitemap INTEGER DEFAULT 0,
    load_time_ms INTEGER,
    page_size_kb INTEGER,
    tech_stack TEXT,
    emails TEXT,
    phones TEXT,
    social_links TEXT,
    issues TEXT,
    score INTEGER DEFAULT 0,
    category_suggestion TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS message_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    channel TEXT NOT NULL,
    category TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    user_agent TEXT,
    ip_address TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_leads_category ON leads(category);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score);
CREATE INDEX IF NOT EXISTS idx_contacts_lead ON contacts(lead_id);
CREATE INDEX IF NOT EXISTS idx_activities_lead ON activities(lead_id);
CREATE INDEX IF NOT EXISTS idx_scans_lead ON website_scans(lead_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);
"""


DEFAULT_TEMPLATES = [
    (
        "Primo contatto - nessun sito",
        "email",
        "Nessun sito",
        "Una presenza online semplice per {company_name}",
        "Ciao, sono Tommaso. Ho visto {company_name} e mi sembra una realta locale interessante. Cercando online non ho trovato un sito ufficiale chiaro: per molte attivita questo significa perdere richieste da chi cerca da telefono e vuole capire subito servizi, orari e contatti.\n\n"
        "Sto proponendo mini siti veloci, puliti e pensati per conversione locale: pagina servizi, contatti rapidi, WhatsApp, mappa, recensioni e base SEO. Posso mandarle una proposta molto concreta e leggera?\n\n"
        "Se non le interessa, me lo dica pure e non la ricontatto.",
    ),
    (
        "Primo contatto - sito migliorabile",
        "email",
        "Sito migliorabile",
        "Piccolo restyling per {company_name}",
        "Ciao, sono Tommaso. Ho dato un'occhiata alla presenza online di {company_name}. Il sito c'e, ma ho notato alcuni punti che potrebbero far perdere fiducia o richieste, soprattutto da mobile: {pain_points}.\n\n"
        "Mi occupo di siti snelli per attivita locali: piu chiari, veloci e facili da contattare. Posso prepararle una mini analisi gratuita con 3 interventi prioritari?\n\n"
        "Se non le interessa, me lo dica pure e non la ricontatto.",
    ),
    (
        "Instagram DM - presenza debole",
        "instagram",
        "Presenza social debole",
        "",
        "Ciao, sono Tommaso. Ho visto la vostra attivita e secondo me avete spazio per rendere la presenza online piu chiara e utile a chi vi scopre da telefono. Posso mandarvi 2 idee pratiche, senza impegno?",
    ),
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def future_iso(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def normalize_email(value):
    return (value or "").strip().lower()


def b64_encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64_decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def hash_password(password):
    if not password or len(password) < 8:
        raise ValueError("Password troppo corta: usa almeno 8 caratteri")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${b64_encode(salt)}${b64_encode(digest)}"


def verify_password(password, stored_hash):
    try:
        algorithm, iterations, salt_value, digest_value = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = b64_decode(salt_value)
        expected = b64_decode(digest_value)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(row):
    if not row:
        return None
    data = to_dict(row)
    data.pop("password_hash", None)
    data["is_active"] = bool(data.get("is_active"))
    data["role_label"] = ROLE_LABELS.get(data.get("role"), data.get("role", ""))
    return data


def can_manage_users(user):
    return bool(user and user.get("role") == "super_admin")


def connect_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_column(conn, table, column, definition):
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def parse_coordinate_text(value):
    text = (value or "").strip()
    match = re.search(r"(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)", text)
    if not match:
        return None, None
    lat = float(match.group(1))
    lon = float(match.group(2))
    if abs(lat) > 90 or abs(lon) > 180:
        return None, None
    return lat, lon


def coerce_float(value):
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def backfill_lead_coordinates(conn):
    rows = conn.execute(
        "SELECT id, address, latitude, longitude FROM leads WHERE deleted_at IS NULL"
    ).fetchall()
    for row in rows:
        if row["latitude"] is not None and row["longitude"] is not None:
            continue
        lat, lon = parse_coordinate_text(row["address"])
        if lat is None or lon is None:
            continue
        conn.execute("UPDATE leads SET latitude = ?, longitude = ? WHERE id = ?", (lat, lon, row["id"]))


def init_db():
    with connect_db() as conn:
        conn.executescript(SCHEMA)
        ensure_column(conn, "leads", "latitude", "REAL")
        ensure_column(conn, "leads", "longitude", "REAL")
        ensure_column(conn, "activities", "assigned_user_id", "INTEGER")
        ensure_column(conn, "activities", "notify_at", "TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_coordinates ON leads(latitude, longitude)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_assignee ON activities(assigned_user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_due ON activities(due_at)")
        backfill_lead_coordinates(conn)
        count = conn.execute("SELECT COUNT(*) AS count FROM message_templates").fetchone()["count"]
        if count == 0:
            stamp = now_iso()
            conn.executemany(
                """
                INSERT INTO message_templates (name, channel, category, subject, body, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [(name, channel, category, subject, body, stamp) for name, channel, category, subject, body in DEFAULT_TEMPLATES],
            )
        ensure_bootstrap_super_admin(conn)


def ensure_bootstrap_super_admin(conn):
    email = normalize_email(BOOTSTRAP_SUPER_ADMIN["email"])
    row = conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
    stamp = now_iso()
    if row:
        conn.execute(
            """
            UPDATE users
            SET role = 'super_admin', is_active = 1, updated_at = ?
            WHERE id = ?
            """,
            (stamp, row["id"]),
        )
        return
    conn.execute(
        """
        INSERT INTO users (email, name, role, password_hash, is_active, created_at, updated_at)
        VALUES (?, ?, 'super_admin', ?, 1, ?, ?)
        """,
        (
            email,
            BOOTSTRAP_SUPER_ADMIN["name"],
            BOOTSTRAP_SUPER_ADMIN["password_hash"],
            stamp,
            stamp,
        ),
    )


def list_users(conn):
    rows = conn.execute(
        """
        SELECT id, email, name, role, is_active, last_login_at, created_at, updated_at
        FROM users
        ORDER BY CASE role WHEN 'super_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, name COLLATE NOCASE
        """
    ).fetchall()
    return [public_user(row) for row in rows]


def list_team_users(conn):
    rows = conn.execute(
        """
        SELECT id, email, name, role, is_active, last_login_at, created_at, updated_at
        FROM users
        WHERE is_active = 1
        ORDER BY CASE role WHEN 'super_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, name COLLATE NOCASE
        """
    ).fetchall()
    return [public_user(row) for row in rows]


def get_user_by_email(conn, email):
    return conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (normalize_email(email),)).fetchone()


def get_user_by_id(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(conn, payload, actor):
    if not can_manage_users(actor):
        raise PermissionError("Solo un super admin puo creare utenti")
    email = normalize_email(payload.get("email"))
    name = (payload.get("name") or "").strip()
    role = (payload.get("role") or "member").strip()
    password = payload.get("password") or ""
    if not email or "@" not in email:
        raise ValueError("Email non valida")
    if not name:
        raise ValueError("Nome obbligatorio")
    if role not in ROLES:
        raise ValueError("Ruolo non valido")
    if get_user_by_email(conn, email):
        raise ValueError("Utente gia presente")
    stamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO users (email, name, role, password_hash, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email,
            name,
            role,
            hash_password(password),
            1 if payload.get("is_active", True) else 0,
            stamp,
            stamp,
        ),
    )
    return public_user(get_user_by_id(conn, cur.lastrowid))


def update_user(conn, user_id, payload, actor):
    if not can_manage_users(actor):
        raise PermissionError("Solo un super admin puo modificare utenti")
    row = get_user_by_id(conn, user_id)
    if not row:
        return None
    current = public_user(row)
    updates = []
    params = []
    if "email" in payload:
        email = normalize_email(payload.get("email"))
        if not email or "@" not in email:
            raise ValueError("Email non valida")
        existing = get_user_by_email(conn, email)
        if existing and existing["id"] != user_id:
            raise ValueError("Email gia usata")
        updates.append("email = ?")
        params.append(email)
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("Nome obbligatorio")
        updates.append("name = ?")
        params.append(name)
    if "role" in payload:
        role = (payload.get("role") or "").strip()
        if role not in ROLES:
            raise ValueError("Ruolo non valido")
        updates.append("role = ?")
        params.append(role)
    if "is_active" in payload:
        active = 1 if payload.get("is_active") else 0
        if user_id == actor.get("id") and not active:
            raise ValueError("Non puoi disattivare il tuo account")
        updates.append("is_active = ?")
        params.append(active)
    if payload.get("password"):
        updates.append("password_hash = ?")
        params.append(hash_password(payload.get("password")))
    if not updates:
        return current
    updates.append("updated_at = ?")
    params.append(now_iso())
    params.append(user_id)
    conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    if "is_active" in payload and not payload.get("is_active"):
        conn.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
    return public_user(get_user_by_id(conn, user_id))


def authenticate_user(conn, email, password):
    row = get_user_by_email(conn, email)
    if not row or not row["is_active"] or not verify_password(password or "", row["password_hash"]):
        return None
    stamp = now_iso()
    conn.execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, row["id"]))
    return public_user(get_user_by_id(conn, row["id"]))


def create_session(conn, user_id, user_agent="", ip_address=""):
    raw_token = secrets.token_urlsafe(36)
    stamp = now_iso()
    expires = future_iso(SESSION_TTL_SECONDS)
    conn.execute(
        """
        INSERT INTO user_sessions (user_id, token_hash, user_agent, ip_address, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, token_hash(raw_token), user_agent[:240], ip_address[:80], stamp, expires),
    )
    return raw_token, expires


def user_from_session_token(conn, raw_token):
    if not raw_token:
        return None
    row = conn.execute(
        """
        SELECT u.*
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
          AND s.expires_at > ?
          AND u.is_active = 1
        LIMIT 1
        """,
        (token_hash(raw_token), now_iso()),
    ).fetchone()
    return public_user(row)


def get_setting(conn, key, default=""):
    if key not in SETTING_KEYS:
        return default
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row or row["value"] is None:
        return default
    return row["value"]


def set_setting(conn, key, value):
    if key not in SETTING_KEYS:
        raise ValueError("Impostazione non supportata")
    stamp = now_iso()
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, stamp),
    )


def resolve_google_api_key(conn):
    return (get_setting(conn, "google_places_api_key") or os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()


def google_places_enabled(conn):
    return bool_setting(conn, "google_places_enabled", False)


def google_places_available(conn):
    return google_places_enabled(conn) and bool(resolve_google_api_key(conn))


def resolve_anthropic_api_key(conn):
    return (get_setting(conn, "anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def resolve_openai_api_key(conn):
    return (get_setting(conn, "openai_api_key") or os.environ.get("OPENAI_API_KEY") or "").strip()


def normalize_anthropic_model(value):
    model = (value or "").strip()
    if not model:
        return DEFAULT_ANTHROPIC_MODEL
    valid = {item["id"] for item in ANTHROPIC_MODEL_OPTIONS}
    return model if model in valid else model


def normalize_ai_provider(value):
    provider = (value or "auto").strip().lower()
    if provider not in AI_PROVIDERS:
        return "auto"
    return provider


def active_ai_provider(conn, require_key=True):
    requested = normalize_ai_provider(get_setting(conn, "ai_provider") or os.environ.get("AI_PROVIDER") or "auto")
    has_anthropic = bool(resolve_anthropic_api_key(conn))
    has_openai = bool(resolve_openai_api_key(conn))
    if requested == "anthropic":
        if has_anthropic:
            return "anthropic"
        if require_key:
            raise ValueError("Configura Claude / Anthropic API key nella pagina Provider")
        return ""
    if requested == "openai":
        if has_openai:
            return "openai"
        if require_key:
            raise ValueError("Configura OpenAI API key nella pagina Provider")
        return ""
    if has_anthropic:
        return "anthropic"
    if has_openai:
        return "openai"
    if require_key:
        raise ValueError("Configura una chiave AI nella pagina Provider")
    return ""


def mask_secret(value):
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def settings_snapshot(conn):
    google_setting = get_setting(conn, "google_places_api_key")
    anthropic_setting = get_setting(conn, "anthropic_api_key")
    openai_setting = get_setting(conn, "openai_api_key")
    google_env = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    anthropic_env = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_env = os.environ.get("OPENAI_API_KEY", "")
    google_key = (google_setting or google_env or "").strip()
    google_enabled = google_places_enabled(conn)
    anthropic_key = (anthropic_setting or anthropic_env or "").strip()
    openai_key = (openai_setting or openai_env or "").strip()
    openai_model = (get_setting(conn, "openai_model") or DEFAULT_OPENAI_MODEL).strip()
    anthropic_model = normalize_anthropic_model(get_setting(conn, "anthropic_model") or DEFAULT_ANTHROPIC_MODEL)
    ai_provider = normalize_ai_provider(get_setting(conn, "ai_provider") or os.environ.get("AI_PROVIDER") or "auto")
    return {
        "google_places_configured": bool(google_key),
        "google_places_enabled": google_enabled,
        "google_places_ready": google_enabled and bool(google_key),
        "google_places_key": mask_secret(google_key),
        "google_places_source": "CRM" if google_setting else ("Mac" if google_env else ""),
        "anthropic_configured": bool(anthropic_key),
        "anthropic_key": mask_secret(anthropic_key),
        "anthropic_source": "CRM" if anthropic_setting else ("Mac" if anthropic_env else ""),
        "anthropic_model": anthropic_model,
        "anthropic_models": ANTHROPIC_MODEL_OPTIONS,
        "openai_configured": bool(openai_key),
        "openai_key": mask_secret(openai_key),
        "openai_source": "CRM" if openai_setting else ("Mac" if openai_env else ""),
        "openai_model": openai_model,
        "ai_provider": ai_provider,
        "ai_provider_active": active_ai_provider(conn, require_key=False),
        "monthly_budget_eur": get_setting(conn, "monthly_budget_eur"),
    }


def save_settings(conn, payload):
    secret_keys = {"google_places_api_key", "anthropic_api_key", "openai_api_key"}
    for key in SETTING_KEYS:
        if key not in payload:
            continue
        value = (payload.get(key) or "").strip()
        if key in secret_keys and not value:
            continue
        if key == "google_places_enabled":
            value = "1" if value.lower() in {"1", "true", "yes", "on", "si", "sì"} else "0"
        if key == "ai_provider":
            value = normalize_ai_provider(value)
        if key == "anthropic_model":
            value = normalize_anthropic_model(value)
        if key == "openai_model" and not value:
            value = DEFAULT_OPENAI_MODEL
        set_setting(conn, key, value)
    return settings_snapshot(conn)


def split_strategy_values(value):
    return [item.strip() for item in re.split(r"[\n,;]+", value or "") if item.strip()]


def bool_setting(conn, key, default=True):
    value = (get_setting(conn, key) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on", "si", "sì"}


def int_setting(conn, key, default, minimum=None, maximum=None):
    try:
        value = int(float(get_setting(conn, key) or default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def payload_int(payload, key, default, minimum=None, maximum=None):
    try:
        value = int(float(payload.get(key) or default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def target_zones(conn):
    zones = split_strategy_values(get_setting(conn, "target_zones"))
    return zones or list(DEFAULT_TARGET_ZONES)


def target_sector_keys(conn):
    configured = split_strategy_values(get_setting(conn, "target_sectors"))
    allowed = {sector["key"] for sector in DISCOVERY_SECTORS}
    sectors = [key for key in configured if key in allowed]
    return sectors or list(DEFAULT_TARGET_SECTORS)


def strategy_categories(conn):
    selected = set(target_sector_keys(conn))
    categories = []
    for sector in DISCOVERY_SECTORS:
        profile = SECTOR_PLAYBOOK.get(sector["key"], {})
        categories.append(
            {
                "key": sector["key"],
                "label": sector["label"],
                "google_type": GOOGLE_SECTOR_TYPES.get(sector["key"], ""),
                "selected": sector["key"] in selected,
                "score_weight": profile.get("weight", 4),
                "default_offer": profile.get("offer", "Audit presenza locale"),
                "reason": profile.get("reason", "buona opportunita locale"),
            }
        )
    return categories


def strategy_snapshot(conn):
    price_floor = int_setting(conn, "openai_price_floor", 450, 0, 50000)
    price_ceiling = int_setting(conn, "openai_price_ceiling", 1800, 0, 50000)
    if price_ceiling and price_floor > price_ceiling:
        price_floor, price_ceiling = price_ceiling, price_floor
    places_limit = int_setting(conn, "places_default_limit", 25, 5, 80)
    only_without_website = bool_setting(conn, "places_only_without_website", True)
    require_contact = bool_setting(conn, "places_require_contact", True)
    sectors = target_sector_keys(conn)
    zones = target_zones(conn)
    return {
        "settings": {
            "target_zones": "\n".join(zones),
            "target_sectors": ",".join(sectors),
            "places_default_limit": places_limit,
            "places_only_without_website": only_without_website,
            "places_require_contact": require_contact,
            "openai_price_floor": price_floor,
            "openai_price_ceiling": price_ceiling,
        },
        "google_places": {
            "zones": zones,
            "categories": strategy_categories(conn),
            "data_fields": GOOGLE_DATA_FIELDS,
            "duplicate_policy": DUPLICATE_POLICY,
            "score_formula": SCORE_RULES,
        },
        "openai": {
            "tasks": OPENAI_TASKS,
            "outputs": OPENAI_OUTPUTS,
            "pricing": {
                "floor_eur": price_floor,
                "ceiling_eur": price_ceiling,
                "default_range": f"{price_floor}-{price_ceiling} EUR" if price_ceiling else f"da {price_floor} EUR",
            },
            "guardrails": OPENAI_GUARDRAILS,
        },
    }


def save_strategy(conn, payload):
    zones = "\n".join(split_strategy_values(payload.get("target_zones") or ""))
    sectors = []
    allowed = {sector["key"] for sector in DISCOVERY_SECTORS}
    incoming = payload.get("target_sectors") or []
    if isinstance(incoming, str):
        incoming = split_strategy_values(incoming)
    for key in incoming:
        if key in allowed and key not in sectors:
            sectors.append(key)
    if not sectors:
        sectors = list(DEFAULT_TARGET_SECTORS)

    set_setting(conn, "target_zones", zones or "\n".join(DEFAULT_TARGET_ZONES))
    set_setting(conn, "target_sectors", ",".join(sectors))
    set_setting(conn, "places_default_limit", str(payload_int(payload, "places_default_limit", 25, 5, 80)))
    set_setting(conn, "places_only_without_website", "1" if payload.get("places_only_without_website") else "0")
    set_setting(conn, "places_require_contact", "1" if payload.get("places_require_contact") else "0")
    set_setting(conn, "openai_price_floor", str(payload_int(payload, "openai_price_floor", 450, 0, 50000)))
    set_setting(conn, "openai_price_ceiling", str(payload_int(payload, "openai_price_ceiling", 1800, 0, 50000)))
    return strategy_snapshot(conn)


def ai_control_value(conn, key):
    return get_setting(conn, key) or DEFAULT_AI_CONTROL.get(key, "")


def ai_control_snapshot(conn):
    settings = {key: ai_control_value(conn, key) for key in DEFAULT_AI_CONTROL}
    return {
        "settings": settings,
        "services": split_strategy_values(settings["ai_services"]),
        "proof_points": split_strategy_values(settings["ai_proof_points"]),
        "followup_plan": split_strategy_values(settings["ai_followup_plan"]),
        "rules": OPENAI_GUARDRAILS,
    }


def save_ai_control(conn, payload):
    for key, default in DEFAULT_AI_CONTROL.items():
        value = (payload.get(key) or "").strip()
        set_setting(conn, key, value or default)
    return ai_control_snapshot(conn)


def ai_strategy_context(conn):
    snapshot = strategy_snapshot(conn)
    ai_control = ai_control_snapshot(conn)
    selected_categories = [
        {
            "label": category["label"],
            "score_weight": category["score_weight"],
            "default_offer": category["default_offer"],
        }
        for category in snapshot["google_places"]["categories"]
        if category["selected"]
    ]
    return {
        "target_zones": snapshot["google_places"]["zones"],
        "target_categories": selected_categories,
        "pricing": snapshot["openai"]["pricing"],
        "tasks": snapshot["openai"]["tasks"],
        "guardrails": snapshot["openai"]["guardrails"],
        "ai_control": {
            "seller_name": ai_control["settings"]["ai_seller_name"],
            "business_name": ai_control["settings"]["ai_business_name"],
            "tone": ai_control["settings"]["ai_tone"],
            "services": ai_control["services"],
            "ideal_customer": ai_control["settings"]["ai_ideal_customer"],
            "offer_focus": ai_control["settings"]["ai_offer_focus"],
            "proof_points": ai_control["proof_points"],
            "message_style": ai_control["settings"]["ai_message_style"],
            "followup_plan": ai_control["followup_plan"],
        },
    }


def info_sections_snapshot():
    return [
        {
            "id": "production",
            "title": "Produzione Fly.io",
            "summary": "Configurazione dell'istanza pubblica del CRM e punti da controllare in deploy.",
            "bullets": [
                f"App Fly.io: {PUBLIC_APP_NAME}",
                f"URL pubblico: {PUBLIC_APP_URL}",
                f"Regione primaria: {PRIMARY_REGION}",
                "Volume persistente montato su /data",
                "Database SQLite in produzione: /data/crm.sqlite3",
                "Avvio server: python3 server.py --host 0.0.0.0 --port 8080",
                "Cookie Secure attivo quando CRM_COOKIE_SECURE=true",
            ],
            "commands": [
                f"fly status -a {PUBLIC_APP_NAME}",
                f"fly logs -a {PUBLIC_APP_NAME} --no-tail",
                f"curl -I {PUBLIC_APP_URL}/",
            ],
        },
        {
            "id": "backup",
            "title": "Backup automatico macOS",
            "summary": "Script locale con login autenticato al CRM, export CSV e retention di 30 giorni.",
            "bullets": [
                "Script locale: backup_crm.py",
                "Cartella backup: ~/crm-backups/",
                "Nome file: crm-backup-YYYY-MM-DD-HHMM.csv",
                "Retention automatica: elimina backup piu vecchi di 30 giorni",
                "Credenziali lette da ~/.crm-backup-env",
                "Il plist launchd usa ~/Library/LaunchAgents/com.leadcrm.backup.plist",
            ],
            "commands": [
                "chmod 600 ~/.crm-backup-env",
                "launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.leadcrm.backup.plist",
                "launchctl kickstart -k gui/$(id -u)/com.leadcrm.backup",
            ],
        },
        {
            "id": "api",
            "title": "Endpoint utili",
            "summary": "Route operative confermate nel backend corrente.",
            "bullets": [
                "Login: POST /api/login con JSON {email, password}",
                "Verifica sessione: GET /api/session",
                "Export CSV: GET /api/export/leads.csv con cookie di sessione",
                "Risposta export: text/csv; charset=utf-8",
                "Campi CSV: id, company_name, sector, city, website, category, stage, priority, score, opportunity, notes, next_follow_up, created_at",
            ],
            "commands": [
                "POST /api/login",
                "GET /api/session",
                "GET /api/export/leads.csv",
            ],
        },
        {
            "id": "assistant",
            "title": "Facundo",
            "summary": "Copilot operativo del CRM con pagina dedicata, knowledge base interna e azioni controllate sul database.",
            "bullets": [
                "Usa la chiave AI gia configurata nella pagina Provider, con priorita al provider attivo",
                "Se la chiave non e disponibile, torna a una risposta locale basata su dati e documentazione interna",
                "La pagina Facundo puo aprire lead, aggiornare pipeline, creare reminder, generare messaggi, fare research e scoring",
                "Puoi salvare note operative, policy, listini e procedure nella knowledge base dedicata",
                "Il bot legge statistiche CRM, lead rilevanti, reminder aperti, strategia e note interne",
            ],
            "commands": [
                "Suggerimento: chiedi quali lead caldi hanno follow-up oggi",
                "Suggerimento: chiedi di spostare un lead in Preventivo",
                "Suggerimento: chiedi di creare un reminder per domani",
            ],
        },
    ]


def assistant_capabilities_snapshot():
    return [
        {
            "title": "Apri e cerca lead",
            "summary": "Trova aziende nel DB per nome o ID e apri subito il lead corretto.",
        },
        {
            "title": "Aggiorna la pipeline",
            "summary": "Puoi cambiare fase, priorita, follow-up, note e altri campi chiave del lead.",
        },
        {
            "title": "Crea reminder",
            "summary": "Genera promemoria operativi agganciati ai lead e assegnati all'utente corrente.",
        },
        {
            "title": "Genera messaggi",
            "summary": "Prepara email o messaggi commerciali con template locali o AI esterna.",
        },
        {
            "title": "Research e scoring",
            "summary": "Lancia research AI e scoring del lead quando il provider e configurato.",
        },
        {
            "title": "Risposte operative",
            "summary": "Spiega backup, deploy, provider, procedure interne e priorita del CRM.",
        },
    ]


def info_snapshot(conn):
    provider = active_ai_provider(conn, require_key=False)
    stats_snapshot = stats(conn)
    return {
        "app_url": PUBLIC_APP_URL,
        "app_name": PUBLIC_APP_NAME,
        "primary_region": PRIMARY_REGION,
        "assistant_name": FACUNDO_NAME,
        "assistant_provider": provider or "locale",
        "assistant_ready": bool(provider),
        "assistant_knowledge": get_setting(conn, "assistant_knowledge"),
        "assistant_capabilities": assistant_capabilities_snapshot(),
        "summary": {
            "total_leads": stats_snapshot["total"],
            "hot_leads": stats_snapshot["hot"],
            "due_followups": stats_snapshot["due"],
            "reminders_due": stats_snapshot["reminders_due"],
            "backups_retention_days": 30,
        },
        "suggested_questions": [
            "Quali lead caldi hanno follow-up oggi?",
            "Apri il lead con score piu alto.",
            "Sposta un lead in Preventivo e crea un reminder per domani.",
            "Come funziona il backup automatico del CRM?",
            "Riassumimi le priorita commerciali del CRM.",
        ],
        "sections": info_sections_snapshot(),
    }


def assistant_keyword_tokens(message):
    tokens = []
    seen = set()
    for raw in re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", (message or "").lower()):
        if len(raw) < 3 or raw in ASSISTANT_STOPWORDS or raw in seen:
            continue
        seen.add(raw)
        tokens.append(raw)
        if len(tokens) >= 6:
            break
    return tokens


def assistant_relevant_leads(conn, message, limit=8):
    tokens = assistant_keyword_tokens(message)
    where_clauses = ["deleted_at IS NULL"]
    params = []
    if tokens:
        token_clauses = []
        for token in tokens:
            like = f"%{token}%"
            token_clauses.append(
                "(lower(company_name) LIKE ? OR lower(COALESCE(sector, '')) LIKE ? OR lower(COALESCE(city, '')) LIKE ? OR lower(COALESCE(notes, '')) LIKE ?)"
            )
            params.extend([like, like, like, like])
        where_clauses.append("(" + " OR ".join(token_clauses) + ")")
    rows = conn.execute(
        f"""
        SELECT id, company_name, sector, city, category, stage, priority, score, website, next_follow_up, updated_at
        FROM leads
        WHERE {' AND '.join(where_clauses)}
        ORDER BY score DESC, updated_at DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [to_dict(row) for row in rows]


def assistant_open_reminders(conn, limit=8):
    rows = conn.execute(
        """
        SELECT
            a.id,
            a.subject,
            a.body,
            a.due_at,
            a.created_at,
            l.id AS lead_id,
            l.company_name,
            u.name AS assigned_user_name
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        LEFT JOIN users u ON u.id = a.assigned_user_id
        WHERE a.kind = 'reminder'
          AND COALESCE(a.completed_at, '') = ''
          AND l.deleted_at IS NULL
        ORDER BY
          CASE WHEN COALESCE(a.due_at, '') = '' THEN 1 ELSE 0 END,
          a.due_at ASC,
          a.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    reminders = []
    for row in rows:
        data = to_dict(row)
        reminders.append(
            {
                "id": data["id"],
                "subject": data.get("subject", ""),
                "body": short_text(data.get("body", ""), 240),
                "due_at": data.get("due_at", ""),
                "lead_id": data.get("lead_id"),
                "company_name": data.get("company_name", ""),
                "assigned_user_name": data.get("assigned_user_name", "") or "Non assegnato",
            }
        )
    return reminders


def assistant_context_snapshot(conn, message):
    strategy = strategy_snapshot(conn)
    providers = settings_snapshot(conn)
    ai_control = ai_control_snapshot(conn)
    leads = assistant_relevant_leads(conn, message)
    reminders = assistant_open_reminders(conn)
    summary = stats(conn)
    return {
        "summary": summary,
        "relevant_leads": [
            {
                "id": lead["id"],
                "company_name": lead.get("company_name", ""),
                "sector": lead.get("sector", ""),
                "city": lead.get("city", ""),
                "category": lead.get("category", ""),
                "stage": lead.get("stage", ""),
                "priority": lead.get("priority", ""),
                "score": lead.get("score", 0),
                "website": lead.get("website", ""),
                "next_follow_up": lead.get("next_follow_up", ""),
            }
            for lead in leads
        ],
        "open_reminders": reminders,
        "providers": {
            "active": providers.get("ai_provider_active", ""),
            "requested": providers.get("ai_provider", ""),
            "anthropic_configured": providers.get("anthropic_configured", False),
            "openai_configured": providers.get("openai_configured", False),
        },
        "strategy": {
            "zones": strategy["google_places"]["zones"],
            "categories": [item["label"] for item in strategy["google_places"]["categories"] if item["selected"]],
            "pricing": strategy["openai"]["pricing"],
        },
        "ai_control": {
            "seller_name": ai_control["settings"]["ai_seller_name"],
            "business_name": ai_control["settings"]["ai_business_name"],
            "tone": ai_control["settings"]["ai_tone"],
            "offer_focus": ai_control["settings"]["ai_offer_focus"],
            "services": ai_control["services"],
        },
        "assistant_knowledge": short_text(get_setting(conn, "assistant_knowledge"), 5000),
        "operational_info": info_sections_snapshot(),
    }


def assistant_chat_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "follow_ups": {"type": "array", "items": {"type": "string"}},
            "used_context": {"type": "array", "items": {"type": "string"}},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": FACUNDO_ACTION_TYPES},
                        "lead_id": {"type": "integer", "minimum": 1},
                        "lead_ref": {"type": "string"},
                        "search": {"type": "string"},
                        "company_name": {"type": "string"},
                        "sector": {"type": "string"},
                        "city": {"type": "string"},
                        "website": {"type": "string"},
                        "source": {"type": "string"},
                        "category": {"type": "string", "enum": ["", *CATEGORIES]},
                        "stage": {"type": "string", "enum": ["", *STAGES]},
                        "priority": {"type": "string", "enum": ["", *PRIORITIES]},
                        "next_follow_up": {"type": "string"},
                        "notes": {"type": "string"},
                        "opportunity": {"type": "string"},
                        "pain_points": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "due_at": {"type": "string"},
                        "notify_at": {"type": "string"},
                        "assigned_user_id": {"type": "integer", "minimum": 1},
                        "channel": {"type": "string", "enum": ["", "email", "whatsapp", "dm", "call"]},
                        "offer": {"type": "string"},
                        "ai": {"type": "boolean"},
                    },
                    "required": ["type"],
                },
            },
        },
        "required": ["answer", "follow_ups", "used_context", "actions"],
    }


def local_assistant_reply(context, message):
    lower = (message or "").lower()
    summary = context["summary"]
    top_leads = context["relevant_leads"][:3]
    follow_ups = []
    used_context = []

    if any(keyword in lower for keyword in {"backup", "csv", "launchd", "plist", "env"}):
        used_context = ["documentazione backup", "endpoint export CSV"]
        answer = (
            "Il backup automatico usa lo script locale backup_crm.py, si autentica con POST /api/login, "
            "verifica la sessione su GET /api/session e scarica l'export da GET /api/export/leads.csv. "
            "I file finiscono in ~/crm-backups/ e quelli piu vecchi di 30 giorni vengono rimossi automaticamente. "
            "Le credenziali vanno in ~/.crm-backup-env e il job macOS usa ~/Library/LaunchAgents/com.leadcrm.backup.plist."
        )
        follow_ups = [
            "Vuoi il riepilogo dei comandi launchctl?",
            "Vuoi sapere quali colonne contiene il CSV?",
        ]
    elif any(keyword in lower for keyword in {"fly", "deploy", "produzione", "volume"}):
        used_context = ["documentazione deploy", "configurazione Fly.io"]
        answer = (
            f"Il CRM pubblico gira su {PUBLIC_APP_URL} nell'app Fly.io {PUBLIC_APP_NAME}, regione {PRIMARY_REGION}. "
            "Il database SQLite in produzione sta su /data/crm.sqlite3 con volume persistente montato su /data. "
            "Il server viene avviato su 0.0.0.0:8080 e i cookie Secure vanno tenuti attivi in produzione."
        )
        follow_ups = [
            "Vuoi il riepilogo dei controlli post-deploy?",
            "Vuoi sapere dove viene salvato il database in produzione?",
        ]
    else:
        used_context = ["stats CRM", "lead rilevanti", "reminder aperti"]
        lead_text = ", ".join(
            f"{lead['company_name']} ({lead['score']}/100, {lead['stage']})"
            for lead in top_leads
            if lead.get("company_name")
        )
        answer = (
            f"Nel CRM ci sono {summary['total']} lead attivi, {summary['hot']} con score alto, "
            f"{summary['due']} follow-up scaduti e {summary['reminders_due']} reminder in scadenza. "
            f"I lead piu rilevanti per questa domanda sono: {lead_text or 'nessun lead specifico trovato nel contesto attuale'}."
        )
        follow_ups = [
            "Vuoi che ti riassuma i lead piu caldi?",
            "Vuoi sapere quali reminder sono aperti?",
        ]

    return {
        "answer": answer,
        "follow_ups": follow_ups,
        "used_context": used_context,
        "actions": [],
    }


def assistant_history_snapshot(payload):
    history = []
    for item in payload.get("history") or []:
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        content = short_text(item.get("content", ""), 1200)
        if role in {"user", "assistant"} and content:
            history.append({"role": role, "content": content})
        if len(history) >= 8:
            break
    return history


def clean_facundo_reference(value):
    cleaned = re.sub(r"^(?:il|la|lead)\s+", "", (value or "").strip(), flags=re.I)
    cleaned = cleaned.strip(" \n\r\t.,:;!?\"'")
    return short_text(cleaned, 180)


def facundo_parse_due_at(text):
    lower = (text or "").lower()
    now = datetime.now().astimezone()
    target = None
    if "dopodomani" in lower:
        target = now + timedelta(days=2)
    elif "domani" in lower:
        target = now + timedelta(days=1)
    elif "oggi" in lower:
        target = now
    else:
        iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lower)
        if iso_match:
            try:
                target = datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            except ValueError:
                target = None
        else:
            ita_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", lower)
            if ita_match:
                year = int(ita_match.group(3) or now.year)
                if year < 100:
                    year += 2000
                try:
                    target = datetime(year, int(ita_match.group(2)), int(ita_match.group(1)))
                except ValueError:
                    target = None
    if not target:
        return ""
    time_match = re.search(r"\b(?:alle|ore)\s*(\d{1,2})(?::(\d{2}))?\b", lower)
    if time_match:
        hour = max(0, min(int(time_match.group(1)), 23))
        minute = max(0, min(int(time_match.group(2) or 0), 59))
        return target.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="seconds")
    return target.date().isoformat()


def facundo_match_details(matches):
    return "\n".join(
        f"#{item['id']} {item['company_name']} · {item.get('city') or '-'} · {item.get('stage') or '-'}"
        for item in matches[:5]
    )


def facundo_lead_matches(conn, reference, limit=5):
    reference = clean_facundo_reference(reference)
    if not reference:
        return []
    try:
        lead_id = int(reference)
    except (TypeError, ValueError):
        lead_id = 0
    if lead_id > 0:
        exact = conn.execute(
            """
            SELECT id, company_name, city, sector, category, stage, priority, score
            FROM leads
            WHERE id = ? AND deleted_at IS NULL
            """,
            (lead_id,),
        ).fetchone()
        if exact:
            return [to_dict(exact)]
    lowered = reference.lower()
    like = f"%{lowered}%"
    rows = conn.execute(
        """
        SELECT id, company_name, city, sector, category, stage, priority, score
        FROM leads
        WHERE deleted_at IS NULL
          AND (
            lower(company_name) = ?
            OR lower(company_name) LIKE ?
            OR lower(COALESCE(city, '')) LIKE ?
            OR lower(COALESCE(sector, '')) LIKE ?
          )
        ORDER BY
          CASE
            WHEN lower(company_name) = ? THEN 0
            WHEN lower(company_name) LIKE ? THEN 1
            ELSE 2
          END,
          score DESC,
          updated_at DESC
        LIMIT ?
        """,
        (lowered, like, like, like, lowered, like, limit),
    ).fetchall()
    return [to_dict(row) for row in rows]


def facundo_resolve_lead(conn, action):
    try:
        lead_id = int(action.get("lead_id") or 0)
    except (TypeError, ValueError):
        lead_id = 0
    if lead_id > 0:
        return get_lead(conn, lead_id), [], str(lead_id)
    reference = action.get("lead_ref") or action.get("company_name") or action.get("search") or ""
    reference = clean_facundo_reference(reference)
    matches = facundo_lead_matches(conn, reference)
    if not matches:
        return None, [], reference
    exact = [row for row in matches if row.get("company_name", "").lower() == reference.lower()]
    if exact:
        return get_lead(conn, exact[0]["id"]), matches, reference
    if len(matches) == 1:
        return get_lead(conn, matches[0]["id"]), matches, reference
    return None, matches, reference


def facundo_action_result(action_type, ok, title, summary, *, lead=None, details="", refresh=False):
    return {
        "type": action_type,
        "ok": bool(ok),
        "title": short_text(title, 120),
        "summary": short_text(summary, 320),
        "details": short_text(details, 2000),
        "lead_id": lead.get("id") if lead else None,
        "lead_name": lead.get("company_name", "") if lead else "",
        "refresh": bool(refresh),
    }


def facundo_resolve_action_lead(conn, action, action_type):
    lead, matches, reference = facundo_resolve_lead(conn, action)
    if lead:
        return lead, None
    if matches:
        return None, facundo_action_result(
            action_type,
            False,
            "Lead ambiguo",
            f"Ho trovato piu lead compatibili con '{reference or 'la richiesta'}'.",
            details=facundo_match_details(matches),
        )
    return None, facundo_action_result(
        action_type,
        False,
        "Lead non trovato",
        f"Non trovo nessun lead compatibile con '{reference or 'la richiesta'}'.",
    )


def local_facundo_plan(context, message):
    raw = short_text(message, 2400).strip()
    lower = raw.lower()

    reminder_match = re.search(r"\b(?:crea|aggiungi|imposta)\s+(?:un\s+)?reminder\s+(?:per|su)\s+(.+?)(?::\s*(.+))?$", raw, re.I)
    if reminder_match:
        lead_ref = clean_facundo_reference(reminder_match.group(1))
        subject = short_text((reminder_match.group(2) or "").strip(), 240)
        if lead_ref and subject:
            due_at = facundo_parse_due_at(raw)
            return {
                "answer": f"Creo il reminder per {lead_ref}.",
                "follow_ups": ["Vuoi che assegni anche una data piu precisa?", "Vuoi aprire il lead dopo la creazione?"],
                "used_context": ["intento reminder", "azioni CRM live"],
                "actions": [
                    {
                        "type": "create_reminder",
                        "lead_ref": lead_ref,
                        "subject": subject,
                        "due_at": due_at,
                    }
                ],
            }
        return {
            "answer": "Posso creare il reminder, ma senza provider AI attivo ho bisogno di una forma esplicita. Esempio: crea reminder per Rossi Serramenti: richiamare domani alle 10.",
            "follow_ups": ["Vuoi che ti mostri un esempio di comando?", "Vuoi aprire prima il lead giusto?"],
            "used_context": ["fallback locale"],
            "actions": [],
        }

    for phrase, stage in FACUNDO_STAGE_ALIASES.items():
        stage_match = re.search(rf"\b(?:sposta|porta|metti|aggiorna)\s+(.+?)\s+(?:in|a)\s+{re.escape(phrase)}\b", raw, re.I)
        if stage_match:
            lead_ref = clean_facundo_reference(stage_match.group(1))
            return {
                "answer": f"Aggiorno {lead_ref} alla fase {stage}.",
                "follow_ups": ["Vuoi che aggiunga anche un follow-up?", "Vuoi aprire il lead dopo l'aggiornamento?"],
                "used_context": ["pipeline CRM", "azioni CRM live"],
                "actions": [{"type": "update_lead", "lead_ref": lead_ref, "stage": stage}],
            }

    priority_match = re.search(r"\b(?:metti|imposta|segna)\s+(.+?)\s+(?:con\s+)?priorit[aà]\s+(alta|media|bassa)\b", raw, re.I)
    if priority_match:
        lead_ref = clean_facundo_reference(priority_match.group(1))
        priority = FACUNDO_PRIORITY_ALIASES.get(priority_match.group(2).lower(), "")
        return {
            "answer": f"Imposto {lead_ref} con priorita {priority}.",
            "follow_ups": ["Vuoi che aggiorni anche la fase?", "Vuoi aprire il lead dopo l'aggiornamento?"],
            "used_context": ["priorita lead", "azioni CRM live"],
            "actions": [{"type": "update_lead", "lead_ref": lead_ref, "priority": priority}],
        }

    open_match = re.search(r"\b(?:apri|mostra|seleziona)\s+(?:il\s+)?lead\s+(.+)$", raw, re.I)
    if open_match:
        lead_ref = clean_facundo_reference(open_match.group(1))
        return {
            "answer": f"Ti preparo il lead {lead_ref}.",
            "follow_ups": ["Vuoi anche un riepilogo del lead?", "Vuoi creare un reminder sullo stesso lead?"],
            "used_context": ["database lead", "azioni CRM live"],
            "actions": [{"type": "open_lead", "lead_ref": lead_ref}],
        }

    message_match = re.search(r"\b(?:scrivi|genera|prepara)\s+(?:un\s+)?messaggio\s+(?:per|su)\s+(.+)$", raw, re.I)
    if message_match:
        lead_ref = clean_facundo_reference(message_match.group(1))
        return {
            "answer": f"Genero una bozza di messaggio per {lead_ref}.",
            "follow_ups": ["Vuoi una versione email o WhatsApp?", "Vuoi prima fare il research del lead?"],
            "used_context": ["messaggi CRM", "azioni CRM live"],
            "actions": [{"type": "generate_message", "lead_ref": lead_ref, "channel": "email", "ai": True}],
        }

    research_match = re.search(r"\b(?:fai|genera|esegui|lancia)?\s*research\s+(?:per|su)\s+(.+)$", raw, re.I)
    if research_match:
        lead_ref = clean_facundo_reference(research_match.group(1))
        return {
            "answer": f"Avvio la research per {lead_ref}.",
            "follow_ups": ["Vuoi anche il messaggio commerciale dopo la research?", "Vuoi aprire il lead aggiornato?"],
            "used_context": ["research lead", "azioni CRM live"],
            "actions": [{"type": "research_lead", "lead_ref": lead_ref, "ai": True}],
        }

    score_match = re.search(r"\b(?:fai|calcola|genera|esegui)?\s*(?:ai\s*)?score\s+(?:per|su)\s+(.+)$", raw, re.I)
    if score_match:
        lead_ref = clean_facundo_reference(score_match.group(1))
        return {
            "answer": f"Calcolo l'AI score per {lead_ref}.",
            "follow_ups": ["Vuoi anche una bozza di messaggio dopo lo score?", "Vuoi aprire il lead aggiornato?"],
            "used_context": ["ai scoring", "azioni CRM live"],
            "actions": [{"type": "score_lead", "lead_ref": lead_ref}],
        }

    create_lead_match = re.search(r"\bcrea(?:mi)?\s+(?:un\s+)?lead(?:\s+per)?\s+(.+)$", raw, re.I)
    if create_lead_match and "reminder" not in lower:
        company_name = clean_facundo_reference(create_lead_match.group(1))
        if company_name:
            return {
                "answer": f"Creo il lead {company_name}.",
                "follow_ups": ["Vuoi aggiungere anche citta o sito?", "Vuoi aprire il lead appena creato?"],
                "used_context": ["creazione lead", "azioni CRM live"],
                "actions": [{"type": "create_lead", "company_name": company_name}],
            }

    if any(keyword in lower for keyword in {"backup", "csv", "launchd", "plist", "env", "fly", "deploy", "produzione", "volume"}):
        return local_assistant_reply(context, message)

    if any(keyword in lower for keyword in {"apri", "sposta", "porta", "metti", "aggiorna", "crea", "genera", "prepara", "research", "score"}):
        return {
            "answer": "Posso farlo, ma senza provider AI attivo ho bisogno di un comando piu esplicito oppure della forma guidata. Esempio: apri lead Rossi Serramenti oppure crea reminder per Rossi Serramenti: richiamare domani alle 10.",
            "follow_ups": ["Vuoi che ti mostri i formati supportati in fallback locale?", "Vuoi che riassuma prima i lead rilevanti?"],
            "used_context": ["fallback locale"],
            "actions": [],
        }

    return local_assistant_reply(context, message)


def execute_facundo_action(conn, action, current_user):
    action_type = (action.get("type") or "").strip()
    current_user = current_user or {}

    if action_type == "search_leads":
        reference = action.get("search") or action.get("lead_ref") or ""
        matches = facundo_lead_matches(conn, reference)
        if not matches:
            return facundo_action_result(action_type, False, "Nessun lead trovato", f"Nessun lead compatibile con '{reference}'.")
        if len(matches) == 1:
            lead = get_lead(conn, matches[0]["id"])
            return facundo_action_result(
                action_type,
                True,
                "Lead trovato",
                f"Trovato un lead compatibile: {lead['company_name']}.",
                lead=lead,
                details=facundo_match_details(matches),
            )
        return facundo_action_result(
            action_type,
            True,
            "Lead compatibili",
            f"Ho trovato {len(matches)} lead compatibili.",
            details=facundo_match_details(matches),
        )

    if action_type == "create_lead":
        company_name = clean_facundo_reference(action.get("company_name") or action.get("lead_ref") or "")
        if not company_name:
            return facundo_action_result(action_type, False, "Creazione non eseguita", "Per creare un lead serve almeno il nome azienda.")
        payload = {
            "company_name": company_name,
            "sector": short_text(action.get("sector", ""), 120),
            "city": short_text(action.get("city", ""), 120),
            "website": short_text(action.get("website", ""), 240),
            "source": short_text(action.get("source", ""), 120),
            "notes": short_text(action.get("notes", ""), 1200),
            "opportunity": short_text(action.get("opportunity", ""), 1200),
            "pain_points": short_text(action.get("pain_points", ""), 800),
            "next_follow_up": short_text(action.get("next_follow_up", ""), 120),
        }
        if action.get("category") in CATEGORIES:
            payload["category"] = action.get("category")
        if action.get("stage") in STAGES:
            payload["stage"] = action.get("stage")
        if action.get("priority") in PRIORITIES:
            payload["priority"] = action.get("priority")
        lead_id = create_lead(conn, payload)
        lead = get_lead(conn, lead_id)
        return facundo_action_result(
            action_type,
            True,
            "Lead creato",
            f"Ho creato il lead {lead['company_name']}.",
            lead=lead,
            details=f"Fase: {lead.get('stage') or '-'}\nPriorita: {lead.get('priority') or '-'}",
            refresh=True,
        )

    lead, error = facundo_resolve_action_lead(conn, action, action_type)
    if error:
        return error

    if action_type == "open_lead":
        return facundo_action_result(
            action_type,
            True,
            "Lead aperto",
            f"Ho trovato {lead['company_name']}.",
            lead=lead,
            details=f"{lead.get('city') or '-'} · {lead.get('stage') or '-'} · score {lead.get('score', 0)}/100",
        )

    if action_type == "update_lead":
        updates = {}
        for key in ["company_name", "sector", "city", "website", "source", "notes", "opportunity", "pain_points", "next_follow_up"]:
            value = short_text(action.get(key, ""), 1600 if key in {"notes", "opportunity", "pain_points"} else 240).strip()
            if value:
                updates[key] = value
        if action.get("category") in CATEGORIES:
            updates["category"] = action.get("category")
        if action.get("stage") in STAGES:
            updates["stage"] = action.get("stage")
        if action.get("priority") in PRIORITIES:
            updates["priority"] = action.get("priority")
        if not updates:
            return facundo_action_result(action_type, False, "Aggiornamento non eseguito", "Non ho ricevuto campi validi da aggiornare.", lead=lead)
        update_lead(conn, lead["id"], updates)
        refreshed = get_lead(conn, lead["id"])
        labels = {
            "stage": "Fase",
            "priority": "Priorita",
            "category": "Categoria",
            "next_follow_up": "Follow-up",
            "city": "Citta",
            "website": "Sito",
            "notes": "Note",
        }
        details = "\n".join(f"{labels.get(key, key)}: {value}" for key, value in updates.items())
        return facundo_action_result(
            action_type,
            True,
            "Lead aggiornato",
            f"Ho aggiornato {refreshed['company_name']}.",
            lead=refreshed,
            details=details,
            refresh=True,
        )

    if action_type == "create_reminder":
        subject = short_text(action.get("subject") or action.get("body") or "", 240).strip()
        if not subject:
            return facundo_action_result(action_type, False, "Reminder non creato", "Per creare un reminder serve almeno un titolo.", lead=lead)
        due_at = short_text(action.get("due_at") or "", 120).strip() or facundo_parse_due_at(f"{subject} {action.get('body') or ''}")
        row = create_reminder(
            conn,
            {
                "lead_id": lead["id"],
                "subject": subject,
                "body": short_text(action.get("body", ""), 1200),
                "due_at": due_at,
                "notify_at": short_text(action.get("notify_at") or due_at, 120),
                "assigned_user_id": action.get("assigned_user_id") or current_user.get("id"),
            },
            current_user,
        )
        reminder = reminder_payload(row)
        return facundo_action_result(
            action_type,
            True,
            "Reminder creato",
            f"Ho creato un reminder per {lead['company_name']}.",
            lead=lead,
            details=f"{reminder.get('subject')}\nScadenza: {reminder.get('due_at') or 'non impostata'}",
            refresh=True,
        )

    if action_type == "generate_message":
        message = build_message(
            conn,
            lead["id"],
            {
                "channel": action.get("channel") if action.get("channel") in {"email", "whatsapp", "dm", "call"} else "email",
                "offer": short_text(action.get("offer", ""), 600),
                "ai": bool(action.get("ai", True)) if active_ai_provider(conn, require_key=False) else False,
            },
        )
        if not message:
            return facundo_action_result(action_type, False, "Messaggio non disponibile", "Non sono riuscito a generare il messaggio.", lead=lead)
        details = "\n\n".join(part for part in [f"Oggetto: {message.get('subject')}" if message.get("subject") else "", message.get("body", "")] if part)
        return facundo_action_result(
            action_type,
            True,
            "Messaggio generato",
            f"Ho preparato una bozza {message.get('channel') or 'email'} per {lead['company_name']}.",
            lead=lead,
            details=details,
        )

    if action_type == "research_lead":
        result = research_lead(conn, lead["id"], {"ai": bool(action.get("ai", True))})
        research = (result or {}).get("research", {}) or {}
        refreshed = (result or {}).get("lead") or get_lead(conn, lead["id"])
        details = "\n".join(
            part
            for part in [
                f"Problema: {research.get('primary_problem')}" if research.get("primary_problem") else "",
                f"Offerta: {research.get('recommended_offer')}" if research.get("recommended_offer") else "",
                f"Canale: {research.get('best_channel')}" if research.get("best_channel") else "",
            ]
            if part
        )
        return facundo_action_result(
            action_type,
            True,
            "Research completata",
            f"Ho aggiornato la research per {refreshed['company_name']}.",
            lead=refreshed,
            details=details or "Research salvata nelle attivita del lead.",
            refresh=True,
        )

    if action_type == "score_lead":
        if not active_ai_provider(conn, require_key=False):
            return facundo_action_result(
                action_type,
                False,
                "AI score non disponibile",
                "Per eseguire lo scoring serve Claude o OpenAI configurato nella pagina Provider.",
                lead=lead,
            )
        result = ai_score_lead(conn, lead["id"])
        refreshed = (result or {}).get("lead") or get_lead(conn, lead["id"])
        analysis = (result or {}).get("analysis", {}) or {}
        details = "\n".join(
            part
            for part in [
                f"Score: {analysis.get('score')}" if analysis.get("score") is not None else "",
                f"Categoria: {analysis.get('category')}" if analysis.get("category") else "",
                f"Priorita: {analysis.get('priority')}" if analysis.get("priority") else "",
                f"Next action: {analysis.get('next_action')}" if analysis.get("next_action") else "",
            ]
            if part
        )
        return facundo_action_result(
            action_type,
            True,
            "AI score completato",
            f"Ho ricalcolato score e priorita di {refreshed['company_name']}.",
            lead=refreshed,
            details=details,
            refresh=True,
        )

    return facundo_action_result(action_type or "unknown", False, "Azione non supportata", "Questa azione non e supportata da Facundo.")


def assistant_chat(conn, payload, current_user=None):
    message = short_text(payload.get("message", ""), 2400)
    if not message.strip():
        raise ValueError("Scrivi un messaggio per Facundo")
    history = assistant_history_snapshot(payload)

    context = assistant_context_snapshot(conn, message)
    provider = active_ai_provider(conn, require_key=False)
    warning = ""
    if provider:
        try:
            result, provider = ai_json(
                conn,
                (
                    f"Sei {FACUNDO_NAME}, copilota operativo di un CRM lead B2B locale. "
                    "Rispondi in italiano, in modo pratico, breve ma utile. "
                    "Usa solo il contesto fornito: dati CRM, strategia, reminder, note interne e documentazione operativa. "
                    "Se un dato non c'e, dichiaralo chiaramente senza inventare. "
                    "Se la richiesta e informativa, rispondi e lascia actions vuoto. "
                    "Se la richiesta richiede un'azione, puoi usare solo le azioni consentite e al massimo 3 azioni. "
                    "Non usare azioni distruttive, non eliminare lead, non cambiare utenti o impostazioni. "
                    "Se manca un dato obbligatorio o il lead non e identificabile con sufficiente sicurezza, non creare azioni e chiedi chiarimento. "
                    "Per lead esistenti preferisci lead_id se disponibile nel contesto; altrimenti usa lead_ref."
                ),
                {
                    "question": message,
                    "history": history,
                    "today": datetime.now().astimezone().date().isoformat(),
                    "allowed_actions": FACUNDO_ACTION_TYPES,
                    "crm": context,
                },
                assistant_chat_schema(),
                "facundo_chat",
            )
        except ValueError as exc:
            result = local_facundo_plan(context, message)
            provider = "locale"
            warning = f"AI esterna non disponibile: {str(exc)[:180]}"
    else:
        result = local_facundo_plan(context, message)
        provider = "locale"
    executed_actions = []
    for action in (result.get("actions") or [])[:3]:
        if isinstance(action, dict):
            executed_actions.append(execute_facundo_action(conn, action, current_user))
    refresh_required = any(item.get("refresh") for item in executed_actions if item.get("ok"))
    selected_lead_id = next((item.get("lead_id") for item in executed_actions if item.get("ok") and item.get("lead_id")), None)
    result["used_context"] = list(result.get("used_context") or [])
    if executed_actions and "azioni CRM live" not in result["used_context"]:
        result["used_context"].append("azioni CRM live")
    result["actions"] = []
    return {
        "reply": result,
        "provider": provider,
        "warning": warning,
        "executed_actions": executed_actions,
        "refresh_required": refresh_required,
        "selected_lead_id": selected_lead_id,
    }


def to_dict(row):
    return dict(row) if row is not None else None


def parse_json_field(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        return "https://" + url
    return url


def compact_list(items, limit=8):
    seen = set()
    cleaned = []
    for item in items:
        value = (item or "").strip()
        key = value.lower()
        if value and key not in seen:
            cleaned.append(value)
            seen.add(key)
        if len(cleaned) >= limit:
            break
    return cleaned


def fetch_json(url, *, data=None, timeout=20, headers=None):
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "TommasoLeadCRM/1.0 (lead discovery locale)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url, payload, *, headers=None, timeout=30):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        return fetch_json(
            url,
            data=body,
            timeout=timeout,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = detail
        try:
            error_payload = json.loads(detail)
            message = error_payload.get("error", {}).get("message") or error_payload.get("message") or detail
        except json.JSONDecodeError:
            pass
        raise ValueError(f"Servizio esterno: {message[:500]}") from exc


def geocode_city(city):
    query = urllib.parse.urlencode(
        {
            "q": city,
            "format": "jsonv2",
            "limit": "1",
            "countrycodes": "it",
            "addressdetails": "1",
        }
    )
    data = fetch_json(f"https://nominatim.openstreetmap.org/search?{query}", timeout=12)
    if not data:
        raise ValueError("Zona non trovata")
    item = data[0]
    south, north, west, east = [float(value) for value in item["boundingbox"]]
    return {
        "display_name": item.get("display_name", city),
        "bbox": (south, west, north, east),
    }


def osm_tag_clause(key, values):
    if values is None:
        return f'["{key}"]'
    pattern = "|".join(re.escape(value) for value in values)
    return f'["{key}"~"^({pattern})$"]'


def build_overpass_query(bbox, sector_key, limit):
    sector_queries = OSM_SECTOR_QUERIES.get(sector_key)
    if not sector_queries:
        raise ValueError("Settore non supportato")
    south, west, north, east = bbox
    bbox_text = f"{south},{west},{north},{east}"
    clauses = []
    for key, values in sector_queries:
        tag_clause = osm_tag_clause(key, values)
        clauses.append(f'node{tag_clause}["name"]({bbox_text});')
        clauses.append(f'way{tag_clause}["name"]({bbox_text});')
        clauses.append(f'relation{tag_clause}["name"]({bbox_text});')
    return f"""
    [out:json][timeout:25];
    (
      {' '.join(clauses)}
    );
    out center tags qt {limit};
    """


def overpass_search(city, sector_key, limit):
    area = geocode_city(city)
    query = build_overpass_query(area["bbox"], sector_key, limit)
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            data = fetch_json(
                endpoint,
                data=body,
                timeout=35,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            return area, data.get("elements", [])
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = exc
            print(f"Overpass request failed via {endpoint}: {exc}", file=sys.stderr)
    if last_error:
        raise ValueError("Ricerca OpenStreetMap temporaneamente non disponibile. Riprova tra poco.") from last_error
    raise ValueError("Ricerca OpenStreetMap temporaneamente non disponibile. Riprova tra poco.")


def first_tag(tags, names):
    for name in names:
        value = (tags.get(name) or "").strip()
        if value:
            return value
    return ""


def normalize_external_url(value):
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("@"):
        return value
    if re.match(r"^https?://", value, re.I):
        return value
    if "." in value and " " not in value:
        return "https://" + value
    return value


def collect_osm_contacts(tags):
    contacts = []
    email = first_tag(tags, ["contact:email", "email"])
    phone = first_tag(tags, ["contact:phone", "phone", "contact:mobile", "mobile"])
    instagram = first_tag(tags, ["contact:instagram", "instagram"])
    facebook = first_tag(tags, ["contact:facebook", "facebook"])
    linkedin = first_tag(tags, ["contact:linkedin", "linkedin"])
    whatsapp = first_tag(tags, ["contact:whatsapp", "whatsapp"])
    if email:
        contacts.append({"type": "email", "value": email, "label": "OpenStreetMap"})
    if phone:
        contacts.append({"type": "telefono", "value": phone, "label": "OpenStreetMap"})
    if instagram:
        contacts.append({"type": "instagram", "value": normalize_external_url(instagram), "label": "OpenStreetMap"})
    if facebook:
        contacts.append({"type": "facebook", "value": normalize_external_url(facebook), "label": "OpenStreetMap"})
    if linkedin:
        contacts.append({"type": "linkedin", "value": normalize_external_url(linkedin), "label": "OpenStreetMap"})
    if whatsapp:
        contacts.append({"type": "whatsapp", "value": normalize_external_url(whatsapp), "label": "OpenStreetMap"})
    return contacts


def format_osm_address(tags, element):
    street = first_tag(tags, ["addr:street"])
    house = first_tag(tags, ["addr:housenumber"])
    postcode = first_tag(tags, ["addr:postcode"])
    city = first_tag(tags, ["addr:city", "addr:town", "addr:village"])
    pieces = []
    if street:
        pieces.append(" ".join(part for part in [street, house] if part))
    if postcode or city:
        pieces.append(" ".join(part for part in [postcode, city] if part))
    if pieces:
        return ", ".join(pieces)
    lat = element.get("lat") or element.get("center", {}).get("lat")
    lon = element.get("lon") or element.get("center", {}).get("lon")
    if lat and lon:
        return f"{lat:.5f}, {lon:.5f}"
    return ""


def osm_element_coordinates(element):
    lat = element.get("lat") or element.get("center", {}).get("lat")
    lon = element.get("lon") or element.get("center", {}).get("lon")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def sector_label(sector_key):
    for sector in DISCOVERY_SECTORS:
        if sector["key"] == sector_key:
            return sector["label"]
    return sector_key


def business_type_from_tags(tags):
    for key in ["amenity", "shop", "craft", "tourism", "office", "leisure"]:
        value = tags.get(key)
        if value:
            return value.replace("_", " ")
    return ""


def lead_exists(conn, candidate):
    source_id = candidate["source_id"]
    by_source = conn.execute(
        "SELECT id FROM leads WHERE deleted_at IS NULL AND source LIKE ? LIMIT 1",
        (f"%{source_id}%",),
    ).fetchone()
    if by_source:
        return by_source["id"]
    city = candidate.get("city", "")
    name = candidate["company_name"]
    by_name = conn.execute(
        """
        SELECT id FROM leads
        WHERE deleted_at IS NULL
          AND lower(company_name) = lower(?)
          AND lower(COALESCE(city, '')) = lower(?)
        LIMIT 1
        """,
        (name, city),
    ).fetchone()
    if by_name:
        return by_name["id"]
    for contact in candidate.get("contacts", []) or []:
        value = (contact.get("value") or "").strip()
        if not value:
            continue
        by_contact = conn.execute(
            """
            SELECT l.id
            FROM contacts c
            JOIN leads l ON l.id = c.lead_id
            WHERE l.deleted_at IS NULL
              AND lower(c.value) = lower(?)
            LIMIT 1
            """,
            (value,),
        ).fetchone()
        if by_contact:
            return by_contact["id"]
    return None


def osm_element_to_candidate(element, city, sector_key):
    tags = element.get("tags") or {}
    name = first_tag(tags, ["name", "brand", "operator"])
    if not name:
        return None
    website = normalize_external_url(first_tag(tags, ["website", "contact:website", "url", "contact:url"]))
    contacts = collect_osm_contacts(tags)
    social_contacts = [contact for contact in contacts if contact["type"] in {"instagram", "facebook", "linkedin", "tiktok", "whatsapp"}]
    business_type = business_type_from_tags(tags)
    address = format_osm_address(tags, element)
    lat, lon = osm_element_coordinates(element)
    element_type = element.get("type", "node")
    source_id = f"OSM {element_type}/{element.get('id')}"
    osm_url = f"https://www.openstreetmap.org/{element_type}/{element.get('id')}"
    no_site = not website
    no_social = not social_contacts
    category = "Nessun sito" if no_site else ("Presenza social debole" if no_social else "Presenza discreta")
    score = 92 if no_site else (58 if no_social else 32)
    issues = []
    if no_site:
        issues.append("Nessun sito ufficiale nei dati pubblici OSM")
    if no_social:
        issues.append("Nessun social trovato nei dati pubblici OSM")
    if not contacts:
        issues.append("Contatti diretti non presenti nei dati pubblici OSM")
    opportunity = build_opportunity(issues, category, score)
    if no_site:
        opportunity = "Proposta consigliata: mini sito locale con contatti rapidi, mappa, servizi, WhatsApp e base SEO."
    contact_summary = ", ".join(f"{contact['type']}: {contact['value']}" for contact in contacts[:3])
    stage = "Pronto da contattare" if contacts else "Da arricchire"
    return {
        "company_name": name,
        "sector": sector_label(sector_key) if not business_type else f"{sector_label(sector_key)} · {business_type}",
        "city": city,
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "website": website,
        "source": f"{source_id} · {osm_url}",
        "source_id": source_id,
        "source_url": osm_url,
        "category": category,
        "stage": stage,
        "priority": "Alta" if score >= 75 and contacts else "Media",
        "score": score,
        "opportunity": opportunity,
        "pain_points": ", ".join(issues),
        "notes": "Lead trovato automaticamente da OpenStreetMap. Verificare dati e consenso prima del contatto.",
        "contacts": contacts,
        "contact_summary": contact_summary or "Da arricchire",
        "has_contact": bool(contacts),
        "has_website": bool(website),
        "has_social": bool(social_contacts),
    }


def discover_osm_leads(conn, payload):
    city = (payload.get("city") or "").strip() or target_zones(conn)[0]
    if not city:
        raise ValueError("Inserisci una zona")
    sector_key = (payload.get("sector") or target_sector_keys(conn)[0]).strip()
    limit = max(5, min(int(payload.get("limit") or int_setting(conn, "places_default_limit", 25, 5, 80)), 80))
    only_without_website = bool(payload.get("only_without_website")) if "only_without_website" in payload else bool_setting(conn, "places_only_without_website", True)
    require_contact = bool(payload.get("require_contact")) if "require_contact" in payload else bool_setting(conn, "places_require_contact", True)
    save = bool(payload.get("save", False))
    search_limit = min(max(limit * 4, 40), 260)
    area, elements = overpass_search(city, sector_key, search_limit)
    candidates = []
    imported = []
    duplicates = 0
    skipped_no_contact = 0
    skipped_with_website = 0
    for element in elements:
        candidate = osm_element_to_candidate(element, city, sector_key)
        if not candidate:
            continue
        if only_without_website and candidate["has_website"]:
            skipped_with_website += 1
            continue
        if require_contact and not candidate["has_contact"]:
            skipped_no_contact += 1
            continue
        existing_id = lead_exists(conn, candidate)
        candidate["existing_id"] = existing_id
        candidate["imported_id"] = None
        if existing_id:
            duplicates += 1
        elif save:
            lead_id = create_lead(conn, candidate)
            candidate["imported_id"] = lead_id
            imported.append(lead_id)
        candidates.append(candidate)
        if len(candidates) >= limit:
            break
    return {
        "area": area["display_name"],
        "sector": sector_label(sector_key),
        "candidates": candidates,
        "count": len(candidates),
        "imported": imported,
        "duplicates": duplicates,
        "skipped_no_contact": skipped_no_contact,
        "skipped_with_website": skipped_with_website,
        "require_contact": require_contact,
    }


def place_text(value):
    if isinstance(value, dict):
        return (value.get("text") or "").strip()
    return (value or "").strip()


def google_place_call(api_key, body):
    return post_json(
        "https://places.googleapis.com/v1/places:searchText",
        body,
        timeout=28,
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": ",".join(
                [
                    "places.id",
                    "places.displayName",
                    "places.formattedAddress",
                    "places.googleMapsUri",
                    "places.location",
                    "places.websiteUri",
                    "places.nationalPhoneNumber",
                    "places.internationalPhoneNumber",
                    "places.rating",
                    "places.userRatingCount",
                    "places.businessStatus",
                    "places.primaryTypeDisplayName",
                    "places.types",
                    "nextPageToken",
                ]
            ),
        },
    )


def google_place_to_candidate(place, city, sector_key):
    name = place_text(place.get("displayName"))
    if not name:
        return None
    website = normalize_external_url(place.get("websiteUri", ""))
    phone = (place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber") or "").strip()
    maps_url = (place.get("googleMapsUri") or "").strip()
    place_id = (place.get("id") or name).strip()
    address = (place.get("formattedAddress") or "").strip()
    location = place.get("location") or {}
    lat = coerce_float(location.get("latitude"))
    lon = coerce_float(location.get("longitude"))
    rating = place.get("rating")
    reviews = place.get("userRatingCount") or 0
    primary_type = place_text(place.get("primaryTypeDisplayName"))
    source_url = maps_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(name + ' ' + city)}"
    source_id = f"Google Places {place_id}"
    contacts = []
    if phone:
        contacts.append({"type": "telefono", "value": phone, "label": "Google Business Profile"})

    profile = SECTOR_PLAYBOOK.get(sector_key, {})
    sector_weight = int(profile.get("weight", 4))
    no_site = not website
    issues = []
    if no_site:
        issues.append("Nessun sito ufficiale trovato su Google Business Profile")
    if not phone:
        issues.append("Telefono non disponibile su Google Business Profile")
    if reviews and int(reviews or 0) < 15:
        issues.append("Poche recensioni Google: reputazione locale da rafforzare")
    if rating and float(rating) < 4 and int(reviews or 0) >= 10:
        issues.append("Reputazione Google migliorabile")
    if no_site:
        score = 76
        category = "Nessun sito"
    else:
        score = 34
        category = "Presenza discreta"
    if phone:
        score += 18
    score += sector_weight
    if reviews and int(reviews or 0) < 15:
        score += 5
    if rating and float(rating) < 4 and int(reviews or 0) >= 10:
        score += 8
    score = min(score, 100)
    notes = [
        "Lead trovato automaticamente da Google Places.",
        "Verificare consenso e canale corretto prima del contatto.",
    ]
    if rating:
        notes.append(f"Rating Google: {rating} su {reviews} recensioni.")
    if place.get("businessStatus"):
        notes.append(f"Stato Google: {place.get('businessStatus')}.")
    opportunity = build_opportunity(issues, category, score)
    if no_site and phone:
        opportunity = "Proposta consigliata: mini sito locale collegato a Google Maps, telefono, WhatsApp, servizi e tracciamento richieste."
    elif profile.get("offer"):
        opportunity = f"Proposta consigliata: {profile['offer']}."
    contact_summary = ", ".join(f"{contact['type']}: {contact['value']}" for contact in contacts[:3])
    sector = sector_label(sector_key)
    if primary_type:
        sector = f"{sector} · {primary_type}"
    stage = "Pronto da contattare" if contacts else "Da arricchire"
    return {
        "company_name": name,
        "sector": sector,
        "city": city,
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "website": website,
        "google_maps_url": maps_url,
        "source": f"{source_id} · {source_url}",
        "source_id": source_id,
        "source_url": source_url,
        "category": category,
        "stage": stage,
        "priority": "Alta" if score >= 75 and contacts else "Media",
        "score": score,
        "opportunity": opportunity,
        "pain_points": ", ".join(issues),
        "notes": " ".join(notes),
        "contacts": contacts,
        "contact_summary": contact_summary,
        "has_contact": bool(contacts),
        "has_website": bool(website),
        "has_social": False,
        "rating": rating,
        "reviews": reviews,
    }


def discover_google_leads(conn, payload):
    if not google_places_enabled(conn):
        raise ValueError("Google Maps e disattivato: usa OpenStreetMap gratis o abilitalo dalla pagina Provider quando vorrai usarlo a consumo")
    city = (payload.get("city") or "").strip() or target_zones(conn)[0]
    if not city:
        raise ValueError("Inserisci una zona")
    api_key = resolve_google_api_key(conn)
    if not api_key:
        raise ValueError("Configura Google Places API key nella pagina Provider")
    sector_key = (payload.get("sector") or target_sector_keys(conn)[0]).strip()
    limit = max(5, min(int(payload.get("limit") or int_setting(conn, "places_default_limit", 25, 5, 60)), 60))
    only_without_website = bool(payload.get("only_without_website")) if "only_without_website" in payload else bool_setting(conn, "places_only_without_website", True)
    require_contact = bool(payload.get("require_contact")) if "require_contact" in payload else bool_setting(conn, "places_require_contact", True)
    save = bool(payload.get("save", False))
    area = geocode_city(city)
    south, west, north, east = area["bbox"]
    body = {
        "textQuery": f"{sector_label(sector_key)} {city}",
        "languageCode": "it",
        "regionCode": "IT",
        "pageSize": min(20, limit),
        "locationRestriction": {
            "rectangle": {
                "low": {"latitude": south, "longitude": west},
                "high": {"latitude": north, "longitude": east},
            }
        },
    }
    included_type = GOOGLE_SECTOR_TYPES.get(sector_key)
    if included_type:
        body["includedType"] = included_type
        body["strictTypeFiltering"] = False

    candidates = []
    imported = []
    duplicates = 0
    skipped_no_contact = 0
    skipped_with_website = 0
    page_token = ""
    pages = 0
    while len(candidates) < limit and pages < 3:
        request_body = dict(body)
        request_body["pageSize"] = min(20, limit - len(candidates))
        if page_token:
            request_body["pageToken"] = page_token
            time.sleep(2)
        data = google_place_call(api_key, request_body)
        pages += 1
        for place in data.get("places", []):
            candidate = google_place_to_candidate(place, city, sector_key)
            if not candidate:
                continue
            if only_without_website and candidate["has_website"]:
                skipped_with_website += 1
                continue
            if require_contact and not candidate["has_contact"]:
                skipped_no_contact += 1
                continue
            existing_id = lead_exists(conn, candidate)
            candidate["existing_id"] = existing_id
            candidate["imported_id"] = None
            if existing_id:
                duplicates += 1
            elif save:
                lead_id = create_lead(conn, candidate)
                candidate["imported_id"] = lead_id
                imported.append(lead_id)
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        page_token = data.get("nextPageToken") or ""
        if not page_token:
            break

    return {
        "provider": "google_places",
        "area": area["display_name"],
        "sector": sector_label(sector_key),
        "candidates": candidates,
        "count": len(candidates),
        "imported": imported,
        "duplicates": duplicates,
        "skipped_no_contact": skipped_no_contact,
        "skipped_with_website": skipped_with_website,
        "require_contact": require_contact,
    }


def lead_coordinates(lead):
    lat = coerce_float(lead.get("latitude"))
    lon = coerce_float(lead.get("longitude"))
    if lat is not None and lon is not None:
        return lat, lon
    return parse_coordinate_text(lead.get("address"))


def map_tone(lead):
    category = lead.get("category") or ""
    score = int(lead.get("score") or 0)
    if category == "Nessun sito":
        return "red"
    if category in {"Sito critico", "Sito migliorabile"} or score >= 75:
        return "orange"
    if category == "Presenza social debole" or score >= 55:
        return "yellow"
    return "green"


def map_opportunities(conn):
    rows = conn.execute(
        """
        SELECT id, company_name, sector, city, address, latitude, longitude, website,
               google_maps_url, source, category, stage, priority, score, opportunity,
               next_follow_up, updated_at
        FROM leads
        WHERE deleted_at IS NULL
        ORDER BY score DESC, updated_at DESC
        LIMIT 1000
        """
    ).fetchall()
    pins = []
    missing = 0
    counts = {"red": 0, "orange": 0, "yellow": 0, "green": 0}
    for row in rows:
        lead = to_dict(row)
        lat, lon = lead_coordinates(lead)
        if lat is None or lon is None:
            missing += 1
            continue
        tone = map_tone(lead)
        counts[tone] += 1
        pins.append(
            {
                "id": lead["id"],
                "company_name": lead.get("company_name", ""),
                "sector": lead.get("sector", ""),
                "city": lead.get("city", ""),
                "address": lead.get("address", ""),
                "latitude": lat,
                "longitude": lon,
                "category": lead.get("category", ""),
                "stage": lead.get("stage", ""),
                "priority": lead.get("priority", ""),
                "score": lead.get("score") or 0,
                "tone": tone,
                "opportunity": lead.get("opportunity", ""),
            }
        )
    if pins:
        lat_values = [pin["latitude"] for pin in pins]
        lon_values = [pin["longitude"] for pin in pins]
        bounds = {
            "south": min(lat_values),
            "north": max(lat_values),
            "west": min(lon_values),
            "east": max(lon_values),
        }
    else:
        bounds = None
    return {
        "pins": pins,
        "counts": counts,
        "bounds": bounds,
        "total": len(pins),
        "without_coordinates": missing,
        "top": pins[:12],
    }


def normalize_sequence(value, fallback):
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        items = split_strategy_values(value or "")
    return items or list(fallback)


def discover_batch_leads(conn, payload):
    provider = (payload.get("provider") or "auto").strip()
    if provider == "auto":
        provider = "google" if google_places_available(conn) else "osm"
    zones = normalize_sequence(payload.get("zones"), target_zones(conn))
    sectors = [key for key in normalize_sequence(payload.get("sectors"), target_sector_keys(conn)) if key in {item["key"] for item in DISCOVERY_SECTORS}]
    if not zones:
        raise ValueError("Configura almeno una zona")
    if not sectors:
        raise ValueError("Configura almeno un settore")
    per_query_limit = max(2, min(int(payload.get("per_query_limit") or 6), 25))
    max_queries = max(1, min(int(payload.get("max_queries") or 12), 40))
    save = bool(payload.get("save", True))
    only_without_website = bool(payload.get("only_without_website")) if "only_without_website" in payload else bool_setting(conn, "places_only_without_website", True)
    require_contact = bool(payload.get("require_contact")) if "require_contact" in payload else bool_setting(conn, "places_require_contact", True)

    summary = {
        "provider": "google_places" if provider == "google" else "osm",
        "queries": 0,
        "count": 0,
        "imported": [],
        "duplicates": 0,
        "skipped_no_contact": 0,
        "skipped_with_website": 0,
        "errors": [],
        "results": [],
        "candidates": [],
    }
    for city in zones:
        for sector_key in sectors:
            if summary["queries"] >= max_queries:
                break
            request = {
                "city": city,
                "sector": sector_key,
                "limit": per_query_limit,
                "only_without_website": only_without_website,
                "require_contact": require_contact,
                "save": save,
            }
            try:
                result = discover_google_leads(conn, request) if provider == "google" else discover_osm_leads(conn, request)
                summary["queries"] += 1
                summary["count"] += result.get("count", 0)
                summary["imported"].extend(result.get("imported", []))
                summary["duplicates"] += result.get("duplicates", 0)
                summary["skipped_no_contact"] += result.get("skipped_no_contact", 0)
                summary["skipped_with_website"] += result.get("skipped_with_website", 0)
                summary["candidates"].extend((result.get("candidates") or [])[: per_query_limit])
                summary["results"].append(
                    {
                        "city": city,
                        "sector": sector_label(sector_key),
                        "count": result.get("count", 0),
                        "imported": len(result.get("imported", [])),
                        "duplicates": result.get("duplicates", 0),
                        "skipped_no_contact": result.get("skipped_no_contact", 0),
                        "skipped_with_website": result.get("skipped_with_website", 0),
                    }
                )
            except Exception as exc:
                summary["queries"] += 1
                summary["errors"].append({"city": city, "sector": sector_label(sector_key), "error": str(exc)})
            if summary["queries"] >= max_queries:
                break
    summary["candidates"] = summary["candidates"][:120]
    return summary


class HTMLProbe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts = []
        self.meta_description = ""
        self.has_viewport = False
        self.generator = ""
        self.links = []
        self.scripts = []
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_map = {str(k).lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            name = attrs_map.get("name", "").lower()
            prop = attrs_map.get("property", "").lower()
            content = attrs_map.get("content", "")
            if name == "description" and content and not self.meta_description:
                self.meta_description = content.strip()
            if name == "viewport":
                self.has_viewport = True
            if name == "generator" and content:
                self.generator = content.strip()
            if prop == "og:description" and content and not self.meta_description:
                self.meta_description = content.strip()
        elif tag in {"a", "link"}:
            href = attrs_map.get("href", "")
            if href:
                self.links.append(href)
        elif tag == "script":
            src = attrs_map.get("src", "")
            if src:
                self.scripts.append(src)

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        text = (data or "").strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        elif len(self.text_parts) < 500:
            self.text_parts.append(text)

    @property
    def title(self):
        return " ".join(self.title_parts).strip()

    @property
    def text(self):
        return " ".join(self.text_parts)


def check_public_file(base_url, file_name):
    try:
        target = urllib.parse.urljoin(base_url, file_name)
        request = urllib.request.Request(
            target,
            method="HEAD",
            headers={"User-Agent": "TommasoLeadCRM/1.0"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return 200 <= response.getcode() < 400
    except Exception:
        return False


def extract_social_links(links, final_url):
    social_domains = [
        "instagram.com",
        "facebook.com",
        "linkedin.com",
        "tiktok.com",
        "youtube.com",
        "wa.me",
        "api.whatsapp.com",
    ]
    found = []
    for link in links:
        absolute = urllib.parse.urljoin(final_url, link)
        host = urllib.parse.urlparse(absolute).netloc.lower()
        if any(domain in host for domain in social_domains):
            found.append(absolute.split("?")[0].rstrip("/"))
    return compact_list(found, limit=10)


def detect_tech_stack(html, probe):
    lowered = html.lower()
    stack = []
    checks = [
        ("WordPress", ["wp-content", "wp-includes", "wordpress"]),
        ("Elementor", ["elementor"]),
        ("WooCommerce", ["woocommerce"]),
        ("Wix", ["wixstatic", "wix.com"]),
        ("Squarespace", ["squarespace"]),
        ("Shopify", ["cdn.shopify", "shopify"]),
        ("Webflow", ["webflow"]),
        ("Bootstrap", ["bootstrap"]),
        ("jQuery", ["jquery"]),
        ("React", ["react", "__react"]),
        ("Next.js", ["__next", "next/static"]),
    ]
    for label, needles in checks:
        if any(needle in lowered for needle in needles):
            stack.append(label)
    if probe.generator:
        stack.append(probe.generator)
    if re.search(r"jquery[-./]1\.", lowered):
        stack.append("jQuery 1.x")
    if "<font " in lowered or "<center" in lowered:
        stack.append("HTML datato")
    if lowered.count("<table") >= 4 and "data-table" not in lowered:
        stack.append("Layout a tabelle")
    return compact_list(stack, limit=10)


def extract_emails(html):
    candidates = re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", html, flags=re.I)
    blocked = {"example.com", "domain.com", "email.com"}
    return compact_list([email for email in candidates if email.split("@")[-1].lower() not in blocked], limit=8)


def extract_phones(text):
    phone_pattern = re.compile(
        r"(?:\+39[\s./-]?)?(?:(?:0\d{1,4}[\s./-]?\d{5,8})|(?:3\d{2}[\s./-]?\d{6,7}))"
    )
    return compact_list(phone_pattern.findall(text), limit=8)


def build_opportunity(issues, category, score):
    if category == "Nessun sito":
        return "Proposta consigliata: mini sito locale con contatti rapidi, mappa, servizi, WhatsApp e base SEO."
    if score >= 75:
        return "Proposta consigliata: restyling rapido orientato a fiducia, mobile e conversione."
    if score >= 55:
        return "Proposta consigliata: pacchetto miglioramento sito con velocita, SEO base e contatti piu evidenti."
    if "Nessun link social trovato nel sito" in issues:
        return "Proposta consigliata: collegare sito e social con contenuti e CTA piu chiari."
    return "Proposta consigliata: audit leggero e miglioramenti mirati alla generazione di richieste."


def score_scan(url, status_code, final_url, html, probe, load_time_ms, page_size_kb, social_links, emails, phones, tech_stack):
    issues = []
    score = 30
    parsed = urllib.parse.urlparse(final_url or url)

    if parsed.scheme != "https":
        issues.append("Sito non in HTTPS")
        score += 13
    if status_code and status_code >= 400:
        issues.append(f"Risposta HTTP problematica: {status_code}")
        score += 20
    if not probe.title:
        issues.append("Titolo pagina assente")
        score += 6
    if not probe.meta_description:
        issues.append("Meta description assente")
        score += 5
    if not probe.has_viewport:
        issues.append("Mobile viewport assente")
        score += 16
    if load_time_ms and load_time_ms > 3500:
        issues.append("Caricamento lento")
        score += 10
    if page_size_kb and page_size_kb > 1500:
        issues.append("Pagina pesante")
        score += 7
    if not social_links:
        issues.append("Nessun link social trovato nel sito")
        score += 5
    if not emails and not phones:
        issues.append("Contatti diretti poco visibili")
        score += 7
    if any(item in tech_stack for item in ["jQuery 1.x", "HTML datato", "Layout a tabelle"]):
        issues.append("Tecnologia o markup datati")
        score += 14
    if "flash" in html.lower() or ".swf" in html.lower():
        issues.append("Elementi Flash o molto vecchi")
        score += 15

    if score >= 75:
        category = "Sito critico"
    elif score >= 55:
        category = "Sito migliorabile"
    elif not social_links:
        category = "Presenza social debole"
    else:
        category = "Presenza discreta"

    return min(score, 100), category, issues


def analyze_website(url):
    original_url = (url or "").strip()
    if not original_url:
        issues = ["Nessun sito ufficiale inserito"]
        return {
            "url": "",
            "final_url": "",
            "status_code": None,
            "title": "",
            "meta_description": "",
            "has_https": False,
            "has_viewport": False,
            "has_robots": False,
            "has_sitemap": False,
            "load_time_ms": None,
            "page_size_kb": None,
            "tech_stack": [],
            "emails": [],
            "phones": [],
            "social_links": [],
            "issues": issues,
            "score": 92,
            "category_suggestion": "Nessun sito",
            "opportunity": build_opportunity(issues, "Nessun sito", 92),
        }

    normalized = normalize_url(original_url)
    attempts = [normalized]
    if normalized.startswith("https://"):
        attempts.append("http://" + normalized[len("https://") :])

    last_error = None
    for target in attempts:
        try:
            request = urllib.request.Request(
                target,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; TommasoLeadCRM/1.0; +local)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            start = time.perf_counter()
            with urllib.request.urlopen(request, timeout=14) as response:
                raw = response.read(1_800_000)
                load_time_ms = int((time.perf_counter() - start) * 1000)
                final_url = response.geturl()
                status_code = response.getcode()
                content_type = response.headers.get("Content-Type", "")
                charset = response.headers.get_content_charset() or "utf-8"
                if "text/html" not in content_type and raw[:100].lower().find(b"<html") == -1:
                    html = raw.decode(charset, errors="replace")
                else:
                    html = raw.decode(charset, errors="replace")

            probe = HTMLProbe()
            probe.feed(html)
            page_size_kb = max(1, int(len(raw) / 1024))
            emails = extract_emails(html)
            phones = extract_phones(probe.text)
            social_links = extract_social_links(probe.links, final_url)
            tech_stack = detect_tech_stack(html, probe)
            has_robots = check_public_file(final_url, "/robots.txt")
            has_sitemap = check_public_file(final_url, "/sitemap.xml")
            score, category, issues = score_scan(
                target,
                status_code,
                final_url,
                html,
                probe,
                load_time_ms,
                page_size_kb,
                social_links,
                emails,
                phones,
                tech_stack,
            )
            if not has_robots:
                issues.append("Robots.txt non trovato")
            if not has_sitemap:
                issues.append("Sitemap XML non trovata")

            return {
                "url": original_url,
                "final_url": final_url,
                "status_code": status_code,
                "title": probe.title[:240],
                "meta_description": probe.meta_description[:500],
                "has_https": urllib.parse.urlparse(final_url).scheme == "https",
                "has_viewport": probe.has_viewport,
                "has_robots": has_robots,
                "has_sitemap": has_sitemap,
                "load_time_ms": load_time_ms,
                "page_size_kb": page_size_kb,
                "tech_stack": tech_stack,
                "emails": emails,
                "phones": phones,
                "social_links": social_links,
                "issues": compact_list(issues, limit=12),
                "score": score,
                "category_suggestion": category,
                "opportunity": build_opportunity(issues, category, score),
            }
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            last_error = str(exc.reason)
        except Exception as exc:
            last_error = str(exc)

    issues = [f"Sito non raggiungibile: {last_error or 'errore sconosciuto'}"]
    return {
        "url": original_url,
        "final_url": "",
        "status_code": None,
        "title": "",
        "meta_description": "",
        "has_https": False,
        "has_viewport": False,
        "has_robots": False,
        "has_sitemap": False,
        "load_time_ms": None,
        "page_size_kb": None,
        "tech_stack": [],
        "emails": [],
        "phones": [],
        "social_links": [],
        "issues": issues,
        "score": 88,
        "category_suggestion": "Sito critico",
        "opportunity": "Proposta consigliata: verificare dominio e presenza online, poi offrire ripristino o nuovo sito leggero.",
    }


def insert_scan(conn, lead_id, scan):
    stamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO website_scans (
            lead_id, url, final_url, status_code, title, meta_description,
            has_https, has_viewport, has_robots, has_sitemap, load_time_ms,
            page_size_kb, tech_stack, emails, phones, social_links, issues,
            score, category_suggestion, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lead_id,
            scan["url"],
            scan["final_url"],
            scan["status_code"],
            scan["title"],
            scan["meta_description"],
            int(bool(scan["has_https"])),
            int(bool(scan["has_viewport"])),
            int(bool(scan["has_robots"])),
            int(bool(scan["has_sitemap"])),
            scan["load_time_ms"],
            scan["page_size_kb"],
            json.dumps(scan["tech_stack"], ensure_ascii=False),
            json.dumps(scan["emails"], ensure_ascii=False),
            json.dumps(scan["phones"], ensure_ascii=False),
            json.dumps(scan["social_links"], ensure_ascii=False),
            json.dumps(scan["issues"], ensure_ascii=False),
            scan["score"],
            scan["category_suggestion"],
            stamp,
        ),
    )
    return cur.lastrowid


def hydrate_scan(row):
    if not row:
        return None
    scan = to_dict(row)
    for key in ["tech_stack", "emails", "phones", "social_links", "issues"]:
        scan[key] = parse_json_field(scan.get(key), [])
    scan["has_https"] = bool(scan.get("has_https"))
    scan["has_viewport"] = bool(scan.get("has_viewport"))
    scan["has_robots"] = bool(scan.get("has_robots"))
    scan["has_sitemap"] = bool(scan.get("has_sitemap"))
    return scan


def create_lead(conn, payload):
    name = (payload.get("company_name") or "").strip()
    if not name:
        raise ValueError("Il nome azienda e obbligatorio")
    stamp = now_iso()
    website = (payload.get("website") or "").strip()
    category = (payload.get("category") or "").strip() or ("Nessun sito" if not website else "Da qualificare")
    stage = (payload.get("stage") or "").strip() or "Nuovo"
    priority = (payload.get("priority") or "").strip() or "Media"
    score = int(payload.get("score") or (92 if category == "Nessun sito" else 0))
    default_opportunity = build_opportunity(["Nessun sito ufficiale inserito"], "Nessun sito", score) if category == "Nessun sito" else ""
    default_pain_points = "Nessun sito ufficiale inserito" if category == "Nessun sito" else ""
    cur = conn.execute(
        """
        INSERT INTO leads (
            company_name, sector, city, address, latitude, longitude, website, google_maps_url, source,
            category, stage, priority, score, opportunity, pain_points, notes,
            next_follow_up, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            payload.get("sector", "").strip(),
            payload.get("city", "").strip(),
            payload.get("address", "").strip(),
            coerce_float(payload.get("latitude")),
            coerce_float(payload.get("longitude")),
            website,
            payload.get("google_maps_url", "").strip(),
            payload.get("source", "").strip(),
            category if category in CATEGORIES else "Da qualificare",
            stage if stage in STAGES else "Nuovo",
            priority if priority in PRIORITIES else "Media",
            max(0, min(score, 100)),
            (payload.get("opportunity") or default_opportunity).strip(),
            (payload.get("pain_points") or default_pain_points).strip(),
            payload.get("notes", "").strip(),
            payload.get("next_follow_up", "").strip(),
            stamp,
            stamp,
        ),
    )
    lead_id = cur.lastrowid
    for contact in payload.get("contacts", []) or []:
        value = (contact.get("value") or "").strip()
        if not value:
            continue
        conn.execute(
            """
            INSERT INTO contacts (lead_id, type, value, label, is_primary, consent_status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                contact.get("type") if contact.get("type") in CONTACT_TYPES else "altro",
                value,
                (contact.get("label") or "").strip(),
                int(bool(contact.get("is_primary"))),
                (contact.get("consent_status") or "Da verificare").strip(),
                (contact.get("notes") or "").strip(),
                stamp,
            ),
        )
    return lead_id


def latest_research_from_activities(activities):
    for activity in activities or []:
        if activity.get("kind") != "research":
            continue
        research = parse_json_field(activity.get("body"), {})
        if research:
            research["created_at"] = activity.get("created_at", "")
            return research
    return None


def get_lead(conn, lead_id):
    lead = conn.execute("SELECT * FROM leads WHERE id = ? AND deleted_at IS NULL", (lead_id,)).fetchone()
    if not lead:
        return None
    data = to_dict(lead)
    data["contacts"] = [
        to_dict(row)
        for row in conn.execute(
            "SELECT * FROM contacts WHERE lead_id = ? ORDER BY is_primary DESC, id DESC",
            (lead_id,),
        )
    ]
    data["activities"] = [
        to_dict(row)
        for row in conn.execute(
            """
            SELECT a.*, u.name AS assigned_user_name, u.email AS assigned_user_email
            FROM activities a
            LEFT JOIN users u ON u.id = a.assigned_user_id
            WHERE a.lead_id = ?
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT 80
            """,
            (lead_id,),
        )
    ]
    data["scans"] = [
        hydrate_scan(row)
        for row in conn.execute(
            "SELECT * FROM website_scans WHERE lead_id = ? ORDER BY created_at DESC, id DESC LIMIT 10",
            (lead_id,),
        )
    ]
    data["assistant"] = build_sales_assistant(data)
    data["research"] = latest_research_from_activities(data["activities"])
    return data


def list_leads(conn, query):
    clauses = ["l.deleted_at IS NULL"]
    params = []
    search = (query.get("search", [""])[0] or "").strip()
    if search:
        like = f"%{search}%"
        clauses.append("(l.company_name LIKE ? OR l.sector LIKE ? OR l.city LIKE ? OR l.website LIKE ? OR l.notes LIKE ?)")
        params.extend([like, like, like, like, like])
    for key in ["stage", "category", "priority"]:
        value = (query.get(key, [""])[0] or "").strip()
        if value and value != "Tutti":
            clauses.append(f"l.{key} = ?")
            params.append(value)
    min_score = (query.get("min_score", [""])[0] or "").strip()
    if min_score:
        clauses.append("l.score >= ?")
        params.append(int(min_score))
    where_sql = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT
            l.*,
            (
                SELECT created_at FROM website_scans ws
                WHERE ws.lead_id = l.id
                ORDER BY ws.created_at DESC, ws.id DESC
                LIMIT 1
            ) AS last_scan_at
        FROM leads l
        WHERE {where_sql}
        ORDER BY
            CASE l.priority WHEN 'Alta' THEN 0 WHEN 'Media' THEN 1 ELSE 2 END,
            l.score DESC,
            l.updated_at DESC
        LIMIT 500
        """,
        params,
    ).fetchall()
    return [to_dict(row) for row in rows]


def list_deleted_leads(conn, query):
    clauses = ["l.deleted_at IS NOT NULL"]
    params = []
    search = (query.get("search", [""])[0] or "").strip()
    if search:
        like = f"%{search}%"
        clauses.append("(l.company_name LIKE ? OR l.sector LIKE ? OR l.city LIKE ? OR l.website LIKE ? OR l.notes LIKE ?)")
        params.extend([like, like, like, like, like])
    where_sql = " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT l.*
        FROM leads l
        WHERE {where_sql}
        ORDER BY l.deleted_at DESC, l.updated_at DESC
        LIMIT 500
        """,
        params,
    ).fetchall()
    return [to_dict(row) for row in rows]


def reminder_payload(row):
    data = to_dict(row)
    data["is_completed"] = bool(data.get("completed_at"))
    data["lead"] = {
        "id": data.pop("lead_id"),
        "company_name": data.pop("lead_company_name", ""),
        "city": data.pop("lead_city", ""),
        "category": data.pop("lead_category", ""),
        "score": data.pop("lead_score", 0),
    }
    data["assigned_user"] = {
        "id": data.get("assigned_user_id"),
        "name": data.pop("assigned_user_name", "") or "Non assegnato",
        "email": data.pop("assigned_user_email", ""),
    }
    return data


def list_reminders(conn):
    rows = conn.execute(
        """
        SELECT
            a.*,
            l.company_name AS lead_company_name,
            l.city AS lead_city,
            l.category AS lead_category,
            l.score AS lead_score,
            u.name AS assigned_user_name,
            u.email AS assigned_user_email
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        LEFT JOIN users u ON u.id = a.assigned_user_id
        WHERE a.kind = 'reminder'
          AND l.deleted_at IS NULL
        ORDER BY
            CASE WHEN COALESCE(a.completed_at, '') = '' THEN 0 ELSE 1 END,
            CASE WHEN COALESCE(a.due_at, '') = '' THEN 1 ELSE 0 END,
            date(a.due_at) ASC,
            a.created_at DESC
        LIMIT 150
        """
    ).fetchall()
    return [reminder_payload(row) for row in rows]


def create_reminder(conn, payload, actor):
    try:
        lead_id = int(payload.get("lead_id") or 0)
    except (TypeError, ValueError):
        lead_id = 0
    lead = conn.execute("SELECT id FROM leads WHERE id = ? AND deleted_at IS NULL", (lead_id,)).fetchone()
    if not lead:
        raise ValueError("Lead non valido")

    subject = (payload.get("subject") or "").strip()
    if not subject:
        raise ValueError("Titolo promemoria obbligatorio")

    try:
        assigned_user_id = int(payload.get("assigned_user_id") or actor.get("id") or 0)
    except (TypeError, ValueError):
        assigned_user_id = actor.get("id")
    assignee = conn.execute("SELECT id FROM users WHERE id = ? AND is_active = 1", (assigned_user_id,)).fetchone()
    if not assignee:
        assigned_user_id = actor.get("id")

    due_at = (payload.get("due_at") or "").strip()
    notify_at = (payload.get("notify_at") or due_at).strip()
    stamp = now_iso()
    cur = conn.execute(
        """
        INSERT INTO activities (
            lead_id, assigned_user_id, kind, subject, body, channel, outcome,
            due_at, notify_at, completed_at, created_at
        )
        VALUES (?, ?, 'reminder', ?, ?, '', 'Da fare', ?, ?, '', ?)
        """,
        (
            lead_id,
            assigned_user_id,
            subject,
            (payload.get("body") or "").strip(),
            due_at,
            notify_at,
            stamp,
        ),
    )
    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (stamp, lead_id))
    return conn.execute(
        """
        SELECT
            a.*,
            l.company_name AS lead_company_name,
            l.city AS lead_city,
            l.category AS lead_category,
            l.score AS lead_score,
            u.name AS assigned_user_name,
            u.email AS assigned_user_email
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        LEFT JOIN users u ON u.id = a.assigned_user_id
        WHERE a.id = ?
        """,
        (cur.lastrowid,),
    ).fetchone()


def update_reminder(conn, reminder_id, payload, actor):
    row = conn.execute(
        """
        SELECT a.*
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        WHERE a.id = ? AND a.kind = 'reminder' AND l.deleted_at IS NULL
        """,
        (reminder_id,),
    ).fetchone()
    if not row:
        return None

    updates = []
    params = []
    if "completed" in payload:
        updates.append("completed_at = ?")
        params.append(now_iso() if payload.get("completed") else "")
        updates.append("outcome = ?")
        params.append("Completato" if payload.get("completed") else "Da fare")
    if "subject" in payload:
        subject = (payload.get("subject") or "").strip()
        if not subject:
            raise ValueError("Titolo promemoria obbligatorio")
        updates.append("subject = ?")
        params.append(subject)
    if "body" in payload:
        updates.append("body = ?")
        params.append((payload.get("body") or "").strip())
    if "due_at" in payload:
        due_at = (payload.get("due_at") or "").strip()
        updates.append("due_at = ?")
        params.append(due_at)
        updates.append("notify_at = ?")
        params.append((payload.get("notify_at") or due_at).strip())
    if "assigned_user_id" in payload:
        try:
            assigned_user_id = int(payload.get("assigned_user_id") or actor.get("id") or 0)
        except (TypeError, ValueError):
            assigned_user_id = actor.get("id")
        assignee = conn.execute("SELECT id FROM users WHERE id = ? AND is_active = 1", (assigned_user_id,)).fetchone()
        if not assignee:
            raise ValueError("Utente assegnato non valido")
        updates.append("assigned_user_id = ?")
        params.append(assigned_user_id)
    if not updates:
        return row
    params.append(reminder_id)
    conn.execute(f"UPDATE activities SET {', '.join(updates)} WHERE id = ?", params)
    return conn.execute(
        """
        SELECT
            a.*,
            l.company_name AS lead_company_name,
            l.city AS lead_city,
            l.category AS lead_category,
            l.score AS lead_score,
            u.name AS assigned_user_name,
            u.email AS assigned_user_email
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        LEFT JOIN users u ON u.id = a.assigned_user_id
        WHERE a.id = ?
        """,
        (reminder_id,),
    ).fetchone()


def contact_channels(lead):
    contacts = lead.get("contacts") or []
    return sorted({contact.get("type", "altro") for contact in contacts if contact.get("value")})


def has_contact_channel(lead):
    return bool(contact_channels(lead))


def sector_value_bonus(sector):
    text = (sector or "").lower()
    high = ["dentist", "dentisti", "hotel", "b&b", "avvocati", "commercialisti", "immobiliari", "palestr"]
    medium = ["ristor", "bar", "beauty", "estet", "parrucch", "officin", "negozi"]
    if any(item in text for item in high):
        return 10
    if any(item in text for item in medium):
        return 6
    return 3


def split_points(value):
    if not value:
        return []
    if isinstance(value, list):
        return compact_list([str(item) for item in value], limit=12)
    return compact_list([part.strip() for part in str(value).split(",")], limit=12)


def lead_local_score(lead):
    score = 18
    website = (lead.get("website") or "").strip()
    category = lead.get("category") or ""
    scans = lead.get("scans") or []
    latest_scan = scans[0] if scans else None
    channels = contact_channels(lead)

    if not website or category == "Nessun sito":
        score += 32
    if category == "Sito critico":
        score += 28
    elif category == "Sito migliorabile":
        score += 20
    elif category == "Presenza social debole":
        score += 14
    if channels:
        score += 18
    if "telefono" in channels or "whatsapp" in channels:
        score += 8
    if "email" in channels:
        score += 5
    if latest_scan:
        score += min(int(latest_scan.get("score") or 0) // 5, 18)
        issues = latest_scan.get("issues") or []
        if "Mobile viewport assente" in issues:
            score += 6
        if "Contatti diretti poco visibili" in issues:
            score += 5
    score += sector_value_bonus(lead.get("sector"))
    if lead.get("stage") in {"Contattato", "Interessato", "Preventivo"}:
        score -= 8
    if lead.get("stage") == "Perso":
        score -= 25
    return max(0, min(score, 100))


def infer_budget(lead, packages):
    score = lead_local_score(lead)
    sector_bonus = sector_value_bonus(lead.get("sector"))
    if score >= 85 and sector_bonus >= 8:
        return "800-1.800 EUR"
    if any(pkg["key"] in {"one_page_site", "restyling"} for pkg in packages):
        return "450-1.200 EUR"
    if any(pkg["key"] in {"google_business", "social_starter"} for pkg in packages):
        return "250-700 EUR"
    return "150-500 EUR"


def recommended_packages(lead):
    category = lead.get("category") or ""
    website = (lead.get("website") or "").strip()
    pain_points = " ".join(split_points(lead.get("pain_points"))).lower()
    latest_scan = (lead.get("scans") or [None])[0]
    scan_issues = latest_scan.get("issues", []) if latest_scan else []
    packages = []

    def add(key, label, reason):
        if key not in {item["key"] for item in packages}:
            packages.append({"key": key, "label": label, "reason": reason})

    if not website or category == "Nessun sito":
        add("one_page_site", "Sito one-page", "manca un sito chiaro da usare come destinazione commerciale")
        add("google_business", "Google Business", "serve una presenza locale coerente con mappa, orari e contatti")
        add("local_seo", "SEO locale base", "puo intercettare ricerche nella zona")
    if category in {"Sito critico", "Sito migliorabile"}:
        add("restyling", "Restyling sito", "il sito esiste ma puo convertire meglio da mobile")
        add("maintenance", "Manutenzione mensile", "serve tenere performance, contenuti e sicurezza sotto controllo")
    if category == "Presenza social debole" or "social" in pain_points or "Nessun link social trovato nel sito" in scan_issues:
        add("social_starter", "Starter Instagram", "la presenza social sembra debole o poco collegata")
        add("photo_shooting", "Shooting foto", "foto migliori aiutano fiducia e conversione")
    if latest_scan and (not latest_scan.get("has_https") or "Tecnologia o markup datati" in scan_issues):
        add("passive_security", "Check sicurezza passivo", "ci sono segnali tecnici migliorabili senza test invasivi")
    if not packages:
        add("audit_light", "Audit leggero", "prima conviene aprire una conversazione con 3 miglioramenti concreti")
    return packages[:5]


def passive_security_points(lead):
    latest_scan = (lead.get("scans") or [None])[0]
    if not latest_scan:
        return [
            {"status": "todo", "label": "Sicurezza passiva non ancora verificata"},
            {"status": "safe", "label": "Nessun test invasivo eseguito"},
        ]
    points = []
    points.append(
        {
            "status": "ok" if latest_scan.get("has_https") else "risk",
            "label": "HTTPS presente" if latest_scan.get("has_https") else "Sito senza HTTPS o certificato non verificato",
        }
    )
    points.append(
        {
            "status": "ok" if latest_scan.get("has_robots") else "warn",
            "label": "Robots.txt presente" if latest_scan.get("has_robots") else "Robots.txt non trovato",
        }
    )
    points.append(
        {
            "status": "ok" if latest_scan.get("has_sitemap") else "warn",
            "label": "Sitemap XML presente" if latest_scan.get("has_sitemap") else "Sitemap XML non trovata",
        }
    )
    tech_stack = latest_scan.get("tech_stack") or []
    if any(item in tech_stack for item in ["jQuery 1.x", "HTML datato", "Layout a tabelle"]):
        points.append({"status": "risk", "label": "Tecnologia o markup datati visibili pubblicamente"})
    if "WordPress" in tech_stack:
        points.append({"status": "warn", "label": "WordPress rilevato: utile proporre manutenzione e aggiornamenti"})
    points.append({"status": "safe", "label": "Controlli solo passivi: nessun exploit, login o test aggressivo"})
    return points[:7]


def build_audit_points(lead):
    points = split_points(lead.get("pain_points"))
    latest_scan = (lead.get("scans") or [None])[0]
    if latest_scan:
        points.extend(latest_scan.get("issues") or [])
    if not (lead.get("website") or "").strip() and "Nessun sito ufficiale trovato" not in points:
        points.append("Nessun sito ufficiale chiaro")
    if not has_contact_channel(lead):
        points.append("Canale di contatto da verificare")
    points = compact_list(points, limit=8)
    if not points:
        points = ["Audit da completare con una scansione sito o verifica manuale"]
    return points


def build_next_actions(lead):
    actions = []
    channels = contact_channels(lead)
    if not channels:
        actions.append("Cercare un contatto diretto prima di qualificarlo")
    elif "telefono" in channels or "whatsapp" in channels:
        actions.append("Preparare messaggio WhatsApp o telefonata breve")
    elif "email" in channels:
        actions.append("Inviare email con mini-audit e proposta leggera")
    else:
        actions.append("Usare il canale social disponibile con messaggio breve")
    if not (lead.get("scans") or []):
        actions.append("Eseguire scansione sito o audit presenza online")
    if not lead.get("next_follow_up"):
        actions.append("Impostare follow-up a 3 giorni dal primo contatto")
    return actions[:4]


def build_sales_assistant(lead):
    local_score = lead_local_score(lead)
    packages = recommended_packages(lead)
    audit_points = build_audit_points(lead)
    channels = contact_channels(lead)
    if local_score >= 80:
        priority = "Alta"
    elif local_score >= 60:
        priority = "Media"
    else:
        priority = "Bassa"
    reasons = []
    if lead.get("category") in {"Nessun sito", "Sito critico", "Sito migliorabile"}:
        reasons.append(lead.get("category"))
    if channels:
        reasons.append("contattabile: " + ", ".join(channels))
    if sector_value_bonus(lead.get("sector")) >= 8:
        reasons.append("settore ad alto valore")
    if not reasons:
        reasons.append("da qualificare con audit leggero")
    return {
        "local_score": local_score,
        "priority": priority,
        "why_interesting": "; ".join(reasons),
        "audit_points": audit_points,
        "passive_security": passive_security_points(lead),
        "packages": packages,
        "estimated_budget": infer_budget(lead, packages),
        "next_actions": build_next_actions(lead),
        "follow_up_plan": ["giorno 0: primo contatto", "giorno 3: follow-up breve", "giorno 7: seconda angolazione", "giorno 30: riattivazione"],
        "sales_angle": (lead.get("opportunity") or build_opportunity(audit_points, lead.get("category") or "Da qualificare", local_score)),
        "contact_channels": channels,
    }


def lead_work_card(lead):
    assistant = build_sales_assistant(lead)
    return {
        "id": lead.get("id"),
        "company_name": lead.get("company_name"),
        "city": lead.get("city"),
        "sector": lead.get("sector"),
        "category": lead.get("category"),
        "stage": lead.get("stage"),
        "score": assistant["local_score"],
        "priority": assistant["priority"],
        "reason": assistant["why_interesting"],
        "next_action": assistant["next_actions"][0] if assistant["next_actions"] else "",
        "budget": assistant["estimated_budget"],
        "has_contact": has_contact_channel(lead),
    }


def sales_workbench(conn):
    leads = [get_lead(conn, row["id"]) for row in list_leads(conn, {})]
    leads = [lead for lead in leads if lead]
    ranked = sorted(leads, key=lambda item: build_sales_assistant(item)["local_score"], reverse=True)
    today = [
        lead
        for lead in ranked
        if lead.get("stage") in {"Nuovo", "Da verificare", "Pronto da contattare"} and has_contact_channel(lead)
    ][:10]
    hot = [lead for lead in ranked if build_sales_assistant(lead)["local_score"] >= 80][:8]
    audit_ready = [
        lead
        for lead in ranked
        if lead.get("category") in {"Nessun sito", "Sito critico", "Sito migliorabile"} and has_contact_channel(lead)
    ][:8]
    followups = [
        lead
        for lead in ranked
        if lead.get("next_follow_up") and lead.get("stage") not in {"Chiuso", "Perso"}
    ][:8]
    no_website = [lead for lead in ranked if lead.get("category") == "Nessun sito"][:8]
    enrich_all = [
        lead
        for lead in ranked
        if lead.get("stage") == "Da arricchire" or not has_contact_channel(lead)
    ]
    enrich_queue = enrich_all[:10]
    return {
        "today": [lead_work_card(lead) for lead in today],
        "hot": [lead_work_card(lead) for lead in hot],
        "audit_ready": [lead_work_card(lead) for lead in audit_ready],
        "followups": [lead_work_card(lead) for lead in followups],
        "no_website": [lead_work_card(lead) for lead in no_website],
        "enrich_queue": [lead_work_card(lead) for lead in enrich_queue],
        "summary": {
            "contactable": sum(1 for lead in leads if has_contact_channel(lead)),
            "audit_ready": len(audit_ready),
            "to_enrich": len(enrich_all),
            "without_website": sum(1 for lead in leads if lead.get("category") == "Nessun sito"),
            "avg_score": round(sum(build_sales_assistant(lead)["local_score"] for lead in leads) / len(leads)) if leads else 0,
        },
    }


def update_lead(conn, lead_id, payload):
    allowed = {
        "company_name",
        "sector",
        "city",
        "address",
        "latitude",
        "longitude",
        "website",
        "google_maps_url",
        "source",
        "category",
        "stage",
        "priority",
        "score",
        "opportunity",
        "pain_points",
        "notes",
        "last_contacted_at",
        "next_follow_up",
    }
    updates = []
    params = []
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key == "score":
            value = max(0, min(int(value or 0), 100))
        elif key in {"latitude", "longitude"}:
            value = coerce_float(value)
        elif value is None:
            value = ""
        elif isinstance(value, str):
            value = value.strip()
        updates.append(f"{key} = ?")
        params.append(value)
    if not updates:
        return
    updates.append("updated_at = ?")
    params.append(now_iso())
    params.append(lead_id)
    conn.execute(f"UPDATE leads SET {', '.join(updates)} WHERE id = ?", params)


def lead_id_list(payload):
    raw_ids = payload.get("ids") or []
    ids = []
    seen = set()
    for raw_id in raw_ids:
        try:
            lead_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if lead_id <= 0 or lead_id in seen:
            continue
        seen.add(lead_id)
        ids.append(lead_id)
        if len(ids) >= 500:
            break
    return ids


def bulk_update_leads(conn, payload):
    ids = lead_id_list(payload)
    if not ids:
        raise ValueError("Seleziona almeno un lead")

    updates_payload = payload.get("updates") or {}
    allowed = {"stage", "category", "priority", "next_follow_up"}
    updates = {}
    for key, value in updates_payload.items():
        if key not in allowed:
            continue
        if value is None:
            value = ""
        if isinstance(value, str):
            value = value.strip()
        if key == "stage" and value and value not in STAGES:
            raise ValueError("Fase non valida")
        if key == "category" and value and value not in CATEGORIES:
            raise ValueError("Categoria non valida")
        if key == "priority" and value and value not in PRIORITIES:
            raise ValueError("Priorita non valida")
        updates[key] = value

    if not updates:
        raise ValueError("Nessuna modifica da applicare")

    placeholders = ",".join("?" for _ in ids)
    assignments = [f"{key} = ?" for key in updates.keys()]
    params = list(updates.values())
    stamp = now_iso()
    params.extend([stamp, *ids])
    cur = conn.execute(
        f"""
        UPDATE leads
        SET {', '.join(assignments)}, updated_at = ?
        WHERE deleted_at IS NULL AND id IN ({placeholders})
        """,
        params,
    )
    return {"updated": cur.rowcount or 0}


def bulk_delete_leads(conn, payload):
    ids = lead_id_list(payload)
    if not ids:
        raise ValueError("Seleziona almeno un lead")
    placeholders = ",".join("?" for _ in ids)
    stamp = now_iso()
    cur = conn.execute(
        f"""
        UPDATE leads
        SET deleted_at = ?, updated_at = ?
        WHERE deleted_at IS NULL AND id IN ({placeholders})
        """,
        [stamp, stamp, *ids],
    )
    return {"deleted": cur.rowcount or 0}


def bulk_restore_leads(conn, payload):
    ids = lead_id_list(payload)
    if not ids:
        raise ValueError("Seleziona almeno un lead")
    placeholders = ",".join("?" for _ in ids)
    stamp = now_iso()
    cur = conn.execute(
        f"""
        UPDATE leads
        SET deleted_at = NULL, updated_at = ?
        WHERE deleted_at IS NOT NULL AND id IN ({placeholders})
        """,
        [stamp, *ids],
    )
    return {"restored": cur.rowcount or 0}


def stats(conn):
    total = conn.execute("SELECT COUNT(*) AS count FROM leads WHERE deleted_at IS NULL").fetchone()["count"]
    hot = conn.execute("SELECT COUNT(*) AS count FROM leads WHERE deleted_at IS NULL AND score >= 75").fetchone()["count"]
    no_site = conn.execute(
        "SELECT COUNT(*) AS count FROM leads WHERE deleted_at IS NULL AND category = 'Nessun sito'"
    ).fetchone()["count"]
    contacted = conn.execute(
        "SELECT COUNT(*) AS count FROM leads WHERE deleted_at IS NULL AND stage IN ('Contattato','Interessato','Preventivo','Chiuso','Vinto')"
    ).fetchone()["count"]
    due = conn.execute(
        """
        SELECT COUNT(*) AS count FROM leads
        WHERE deleted_at IS NULL
          AND next_follow_up IS NOT NULL
          AND next_follow_up != ''
          AND date(next_follow_up) <= date('now')
        """
    ).fetchone()["count"]
    reminders_due = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        WHERE a.kind = 'reminder'
          AND l.deleted_at IS NULL
          AND COALESCE(a.completed_at, '') = ''
          AND COALESCE(a.due_at, '') != ''
          AND date(a.due_at) <= date('now')
        """
    ).fetchone()["count"]
    to_enrich = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM leads l
        WHERE l.deleted_at IS NULL
          AND (
            l.stage = 'Da arricchire'
            OR NOT EXISTS (
              SELECT 1 FROM contacts c
              WHERE c.lead_id = l.id
                AND COALESCE(c.value, '') != ''
            )
          )
        """
    ).fetchone()["count"]
    by_stage = {row["stage"]: row["count"] for row in conn.execute(
        "SELECT stage, COUNT(*) AS count FROM leads WHERE deleted_at IS NULL GROUP BY stage"
    )}
    by_category = {row["category"]: row["count"] for row in conn.execute(
        "SELECT category, COUNT(*) AS count FROM leads WHERE deleted_at IS NULL GROUP BY category"
    )}
    return {
        "total": total,
        "hot": hot,
        "no_site": no_site,
        "contacted": contacted,
        "due": due,
        "reminders_due": reminders_due,
        "to_enrich": to_enrich,
        "by_stage": by_stage,
        "by_category": by_category,
    }


def choose_template(conn, channel, category):
    template = conn.execute(
        """
        SELECT * FROM message_templates
        WHERE channel = ? AND (category = ? OR category IS NULL OR category = '')
        ORDER BY CASE WHEN category = ? THEN 0 ELSE 1 END, id
        LIMIT 1
        """,
        (channel, category, category),
    ).fetchone()
    if not template:
        template = conn.execute("SELECT * FROM message_templates ORDER BY id LIMIT 1").fetchone()
    return to_dict(template)


def short_text(value, limit=900):
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def lead_ai_context(lead):
    contacts = lead.get("contacts") or []
    latest_scan = (lead.get("scans") or [None])[0]
    assistant = lead.get("assistant") or build_sales_assistant(lead)
    return {
        "company_name": lead.get("company_name", ""),
        "sector": lead.get("sector", ""),
        "city": lead.get("city", ""),
        "address": lead.get("address", ""),
        "website": lead.get("website", ""),
        "google_maps_url": lead.get("google_maps_url", ""),
        "source": short_text(lead.get("source", ""), 400),
        "category": lead.get("category", ""),
        "stage": lead.get("stage", ""),
        "priority": lead.get("priority", ""),
        "current_score": lead.get("score", 0),
        "opportunity": short_text(lead.get("opportunity", ""), 700),
        "pain_points": short_text(lead.get("pain_points", ""), 700),
        "notes": short_text(lead.get("notes", ""), 700),
        "contact_channels": sorted({contact.get("type", "altro") for contact in contacts if contact.get("value")}),
        "has_email": any(contact.get("type") == "email" for contact in contacts),
        "has_phone": any(contact.get("type") in {"telefono", "whatsapp"} for contact in contacts),
        "latest_scan": {
            "score": latest_scan.get("score"),
            "category": latest_scan.get("category_suggestion"),
            "issues": latest_scan.get("issues", []),
            "tech_stack": latest_scan.get("tech_stack", []),
            "title": latest_scan.get("title", ""),
            "meta_description": latest_scan.get("meta_description", ""),
            "load_time_ms": latest_scan.get("load_time_ms"),
            "has_https": latest_scan.get("has_https"),
            "has_viewport": latest_scan.get("has_viewport"),
        }
        if latest_scan
        else None,
        "local_assistant": {
            "score": assistant.get("local_score"),
            "priority": assistant.get("priority"),
            "why_interesting": assistant.get("why_interesting"),
            "audit_points": assistant.get("audit_points", []),
            "packages": assistant.get("packages", []),
            "estimated_budget": assistant.get("estimated_budget"),
            "next_actions": assistant.get("next_actions", []),
        },
    }


def response_text(data):
    if data.get("output_text"):
        return data["output_text"]
    parts = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and content.get("text"):
                parts.append(content["text"])
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Risposta AI vuota")
    return text


def parse_json_response(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("Risposta AI non valida")
        return json.loads(match.group(0))


def openai_json(conn, system_prompt, user_payload, schema, name):
    api_key = resolve_openai_api_key(conn)
    if not api_key:
        raise ValueError("Configura OpenAI API key nella pagina Provider")
    model = (get_setting(conn, "openai_model") or DEFAULT_OPENAI_MODEL).strip()
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    data = post_json(
        "https://api.openai.com/v1/responses",
        payload,
        timeout=45,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    text = response_text(data)
    return parse_json_response(text)


def anthropic_text(conn, system_prompt, user_payload):
    api_key = resolve_anthropic_api_key(conn)
    if not api_key:
        raise ValueError("Configura Claude / Anthropic API key nella pagina Provider")
    model = (get_setting(conn, "anthropic_model") or DEFAULT_ANTHROPIC_MODEL).strip()
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            }
        ],
    }
    data = post_json(
        "https://api.anthropic.com/v1/messages",
        payload,
        timeout=45,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
    )
    parts = []
    for block in data.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
            parts.append(block["text"])
        elif isinstance(block, dict) and block.get("text"):
            parts.append(block["text"])
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Risposta Claude vuota")
    return text


def anthropic_json(conn, system_prompt, user_payload, schema, name):
    schema_prompt = (
        f"{system_prompt}\n\n"
        "Rispondi esclusivamente con JSON valido, senza markdown e senza testo fuori dal JSON. "
        "Il JSON deve rispettare questo schema:\n"
        f"{json.dumps({'name': name, 'schema': schema}, ensure_ascii=False)}"
    )
    return parse_json_response(anthropic_text(conn, schema_prompt, user_payload))


def ai_json(conn, system_prompt, user_payload, schema, name):
    provider = active_ai_provider(conn)
    if provider == "anthropic":
        return anthropic_json(conn, system_prompt, user_payload, schema, name), provider
    return openai_json(conn, system_prompt, user_payload, schema, name), provider


def ai_score_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "category": {"type": "string", "enum": CATEGORIES},
            "priority": {"type": "string", "enum": PRIORITIES},
            "opportunity": {"type": "string"},
            "pain_points": {"type": "array", "items": {"type": "string"}},
            "pitch_angle": {"type": "string"},
            "recommended_offer": {"type": "string"},
            "package_recommendation": {"type": "string"},
            "price_recommendation": {"type": "string"},
            "objections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "objection": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "required": ["objection", "answer"],
                },
            },
            "next_action": {"type": "string"},
            "outreach_subject": {"type": "string"},
            "outreach_body": {"type": "string"},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "required": [
            "score",
            "category",
            "priority",
            "opportunity",
            "pain_points",
            "pitch_angle",
            "recommended_offer",
            "package_recommendation",
            "price_recommendation",
            "objections",
            "next_action",
            "outreach_subject",
            "outreach_body",
            "confidence",
        ],
    }


def ai_message_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "channel": {"type": "string"},
            "cta": {"type": "string"},
            "follow_up": {"type": "string"},
        },
        "required": ["subject", "body", "channel", "cta", "follow_up"],
    }


def lead_research_schema():
    objection_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "objection": {"type": "string"},
            "answer": {"type": "string"},
        },
        "required": ["objection", "answer"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "business_summary": {"type": "string"},
            "known_facts": {"type": "array", "items": {"type": "string"}},
            "inferred_signals": {"type": "array", "items": {"type": "string"}},
            "to_verify": {"type": "array", "items": {"type": "string"}},
            "primary_problem": {"type": "string"},
            "opportunity_reason": {"type": "string"},
            "recommended_offer": {"type": "string"},
            "package_recommendation": {"type": "string"},
            "price_recommendation": {"type": "string"},
            "best_channel": {"type": "string"},
            "opening_message": {"type": "string"},
            "objections": {"type": "array", "items": objection_schema},
            "next_steps": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "required": [
            "business_summary",
            "known_facts",
            "inferred_signals",
            "to_verify",
            "primary_problem",
            "opportunity_reason",
            "recommended_offer",
            "package_recommendation",
            "price_recommendation",
            "best_channel",
            "opening_message",
            "objections",
            "next_steps",
            "confidence",
        ],
    }


def best_channel_for_lead(lead):
    channels = contact_channels(lead)
    for preferred in ["whatsapp", "telefono", "email", "instagram", "facebook", "linkedin", "tiktok"]:
        if preferred in channels:
            return preferred
    return channels[0] if channels else "da trovare"


def local_opening_message(lead, control, assistant, best_channel):
    seller = control["settings"]["ai_seller_name"]
    offer = control["settings"]["ai_offer_focus"]
    company = lead.get("company_name") or "la vostra attivita"
    problem = (assistant.get("audit_points") or ["presenza online migliorabile"])[0]
    problem_lower = problem.lower()
    if "nessun sito" in problem_lower:
        friendly_problem = "la presenza online, perche non trovo un sito ufficiale chiaro"
    elif "social" in problem_lower:
        friendly_problem = "il collegamento tra sito, social e contatti"
    elif "contatti" in problem_lower:
        friendly_problem = "la visibilita dei contatti"
    else:
        friendly_problem = problem_lower
    if best_channel == "email":
        return (
            f"Ciao, sono {seller}. Ho visto {company} online e mi sembra ci sia spazio per rendere piu chiara la presenza digitale. "
            f"In particolare ho notato questo punto: {problem}. Posso mandarle una mini proposta concreta su {offer}?"
        )
    return (
        f"Ciao, sono {seller}. Ho visto {company} online: secondo me c'e margine per migliorare {friendly_problem}. "
        f"Posso mandarvi 2 idee pratiche, senza impegno?"
    )


def local_lead_research(conn, lead):
    control = ai_control_snapshot(conn)
    assistant = lead.get("assistant") or build_sales_assistant(lead)
    channels = contact_channels(lead)
    best_channel = best_channel_for_lead(lead)
    packages = assistant.get("packages") or []
    first_package = packages[0] if packages else {"label": "Audit leggero", "reason": "serve aprire una conversazione"}
    facts = compact_list(
        [
            f"Azienda: {lead.get('company_name')}" if lead.get("company_name") else "",
            f"Settore: {lead.get('sector')}" if lead.get("sector") else "",
            f"Zona: {lead.get('city')}" if lead.get("city") else "",
            "Sito presente" if lead.get("website") else "Sito non presente nel CRM",
            "Canali: " + ", ".join(channels) if channels else "Nessun canale di contatto salvato",
            f"Categoria CRM: {lead.get('category')}" if lead.get("category") else "",
        ],
        limit=8,
    )
    inferred = compact_list(
        [
            assistant.get("why_interesting", ""),
            "lead ad alta priorita commerciale" if assistant.get("local_score", 0) >= 80 else "",
            "probabile bisogno di presenza locale piu chiara" if lead.get("category") in {"Nessun sito", "Sito critico", "Sito migliorabile"} else "",
            first_package.get("reason", ""),
        ],
        limit=8,
    )
    to_verify = compact_list(
        [
            "verificare consenso e canale corretto prima del contatto",
            "verificare decisore o titolare",
            "verificare se esistono social o sito non rilevati",
            "verificare budget e urgenza",
        ],
        limit=8,
    )
    audit_points = assistant.get("audit_points") or build_audit_points(lead)
    primary_problem = audit_points[0] if audit_points else "presenza digitale da qualificare"
    research = {
        "business_summary": f"{lead.get('company_name', 'Lead locale')} e un lead {lead.get('sector') or 'locale'} in zona {lead.get('city') or 'da verificare'}.",
        "known_facts": facts,
        "inferred_signals": inferred,
        "to_verify": to_verify,
        "primary_problem": primary_problem,
        "opportunity_reason": assistant.get("why_interesting") or lead.get("opportunity") or "Da qualificare con audit leggero",
        "recommended_offer": control["settings"]["ai_offer_focus"] or lead.get("opportunity") or first_package.get("label", ""),
        "package_recommendation": first_package.get("label", "Audit leggero"),
        "price_recommendation": assistant.get("estimated_budget") or strategy_snapshot(conn)["openai"]["pricing"]["default_range"],
        "best_channel": best_channel,
        "opening_message": local_opening_message(lead, control, assistant, best_channel),
        "objections": [
            {"objection": "Costa troppo", "answer": "Partirei da una versione leggera, con prezzo chiaro e obiettivo semplice: rendere contatti e servizi piu facili da trovare."},
            {"objection": "Abbiamo gia qualcuno", "answer": "Perfetto, allora puo essere utile solo una mini analisi esterna con 2-3 punti pratici da confrontare."},
            {"objection": "Non ci serve il sito", "answer": "Ci sta. Il punto non e avere un sito per forza, ma non perdere chi vi cerca da telefono e vuole contattarvi subito."},
        ],
        "next_steps": assistant.get("next_actions") or ["trovare contatto", "preparare mini audit", "inviare primo messaggio"],
        "confidence": 78 if channels else 58,
        "generated_by": "locale",
        "warning": "" if channels else "Lead da arricchire: manca un canale di contatto diretto.",
    }
    return research


def research_lead(conn, lead_id, payload=None):
    payload = payload or {}
    lead = get_lead(conn, lead_id)
    if not lead:
        return None
    use_ai = bool(payload.get("ai", True))
    warning = ""
    if use_ai and active_ai_provider(conn, require_key=False):
        try:
            result, provider = ai_json(
                conn,
                (
                    "Sei un AI lead researcher per un freelance italiano che vende siti, social e presenza digitale locale. "
                    "Usa solo dati presenti nel CRM. Dividi fatti certi, segnali inferiti e dati da verificare. "
                    "Non inventare contatti, recensioni, social o dettagli aziendali. "
                    "Produci una scheda commerciale concreta, breve, vendibile e rispettosa."
                ),
                {"lead": lead_ai_context(lead), "crm_strategy": ai_strategy_context(conn)},
                lead_research_schema(),
                "lead_research",
            )
            result["generated_by"] = provider
            result["warning"] = ""
        except ValueError as exc:
            result = local_lead_research(conn, lead)
            warning = f"AI esterna non disponibile: {str(exc)[:180]}"
            result["warning"] = warning
    else:
        result = local_lead_research(conn, lead)
    stamp = now_iso()
    conn.execute(
        """
        INSERT INTO activities (lead_id, kind, subject, body, channel, outcome, created_at)
        VALUES (?, 'research', 'AI Lead Research', ?, 'crm', 'Completato', ?)
        """,
        (lead_id, json.dumps(result, ensure_ascii=False), stamp),
    )
    return {"research": result, "lead": get_lead(conn, lead_id), "warning": warning}


def ai_score_lead(conn, lead_id):
    lead = get_lead(conn, lead_id)
    if not lead:
        return None
    context = lead_ai_context(lead)
    result, provider = ai_json(
        conn,
        (
            "Sei un sales analyst per un freelance italiano che vende siti, social e presenza digitale locale. "
            "Valuta solo informazioni disponibili nel CRM, non inventare contatti o fatti. "
            "Dai priorita alta ai lead senza sito ma con canale contattabile. "
            "Usa il range prezzo e i pacchetti del CRM quando proponi un'offerta. "
            "Scrivi in italiano, tono concreto, breve e rispettoso."
        ),
        {"lead": context, "crm_strategy": ai_strategy_context(conn)},
        ai_score_schema(),
        "lead_ai_score",
    )
    result["provider"] = provider
    score = max(0, min(int(result.get("score") or 0), 100))
    category = result.get("category") if result.get("category") in CATEGORIES else lead.get("category")
    priority = result.get("priority") if result.get("priority") in PRIORITIES else lead.get("priority")
    pain_points = compact_list([str(item) for item in result.get("pain_points", [])], limit=8)
    stamp = now_iso()
    conn.execute(
        """
        UPDATE leads
        SET score = ?, category = ?, priority = ?, opportunity = ?, pain_points = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            score,
            category,
            priority,
            short_text(result.get("opportunity", ""), 1200),
            ", ".join(pain_points),
            stamp,
            lead_id,
        ),
    )
    activity_body = json.dumps(
        {
            "score": score,
            "confidence": result.get("confidence"),
            "pitch_angle": result.get("pitch_angle"),
            "recommended_offer": result.get("recommended_offer"),
            "package_recommendation": result.get("package_recommendation"),
            "price_recommendation": result.get("price_recommendation"),
            "objections": result.get("objections") or [],
            "next_action": result.get("next_action"),
            "outreach_subject": result.get("outreach_subject"),
            "outreach_body": result.get("outreach_body"),
            "provider": provider,
        },
        ensure_ascii=False,
    )
    conn.execute(
        """
        INSERT INTO activities (lead_id, kind, subject, body, channel, outcome, created_at)
        VALUES (?, 'ai', 'AI scoring', ?, 'crm', 'Completato', ?)
        """,
        (lead_id, activity_body, stamp),
    )
    return {"analysis": result, "lead": get_lead(conn, lead_id)}


def build_ai_message(conn, lead, payload):
    channel = payload.get("channel") or "email"
    offer = (payload.get("offer") or "").strip()
    context = lead_ai_context(lead)
    result, provider = ai_json(
        conn,
        (
            "Sei un copywriter commerciale italiano per outreach B2B locale. "
            "Scrivi messaggi brevi, personali, senza promesse aggressive e senza fingere relazioni. "
            "Se mancano prove, usa formule caute come 'ho visto online' o 'mi sembra'. "
            "L'obiettivo e ottenere una risposta, non chiudere subito una vendita. "
            "Rispetta il pacchetto e il range prezzo consigliato dal CRM quando utili."
        ),
        {"lead": context, "channel": channel, "offer": offer, "crm_strategy": ai_strategy_context(conn)},
        ai_message_schema(),
        "lead_outreach_message",
    )
    return {
        "subject": result.get("subject", ""),
        "body": result.get("body", ""),
        "channel": result.get("channel") or channel,
        "template": "AI",
        "cta": result.get("cta", ""),
        "follow_up": result.get("follow_up", ""),
        "provider": provider,
    }


def build_message(conn, lead_id, payload):
    lead = get_lead(conn, lead_id)
    if not lead:
        return None
    if payload.get("ai"):
        return build_ai_message(conn, lead, payload)
    channel = payload.get("channel") or "email"
    offer = (payload.get("offer") or "").strip()
    template = choose_template(conn, channel, lead.get("category") or "")
    pain_points = lead.get("pain_points") or ""
    if not pain_points and lead.get("scans"):
        issues = lead["scans"][0].get("issues", [])
        pain_points = ", ".join(issues[:3])
    if not pain_points:
        pain_points = "chiarezza, velocita e contatti piu visibili"
    values = {
        "company_name": lead.get("company_name") or "la vostra attivita",
        "city": lead.get("city") or "",
        "sector": lead.get("sector") or "attivita locale",
        "pain_points": pain_points,
        "offer": offer or "una proposta concreta e leggera",
    }
    subject = (template.get("subject") or "").format(**values)
    body = (template.get("body") or "").format(**values)
    if offer:
        body += f"\n\nIdea di offerta: {offer}"
    return {"subject": subject, "body": body, "channel": channel, "template": template.get("name")}


def export_csv(conn):
    rows = list_leads(conn, {})
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
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
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    return output.getvalue()


class CRMHandler(BaseHTTPRequestHandler):
    server_version = "TommasoLeadCRM/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def cookie_value(self, name):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie[name].value if name in cookie else ""

    def session_cookie_header(self, token, max_age=SESSION_TTL_SECONDS):
        parts = [
            f"{SESSION_COOKIE}={token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            f"Max-Age={int(max_age)}",
        ]
        if os.environ.get("CRM_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}:
            parts.append("Secure")
        return "; ".join(parts)

    def current_user(self, conn):
        conn.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (now_iso(),))
        return user_from_session_token(conn, self.cookie_value(SESSION_COOKIE))

    def require_user(self, conn):
        user = self.current_user(conn)
        if not user:
            self.send_error_json("Accesso richiesto", status=401)
            return None
        return user

    def require_super_admin(self, user):
        if not can_manage_users(user):
            self.send_error_json("Solo un super admin puo gestire gli utenti", status=403)
            return False
        return True

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_json(self, payload, status=200, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, status=200, content_type="text/plain; charset=utf-8", headers=None):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status=status)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                return self.handle_api_get(path, query)
            return self.serve_static(path)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(str(exc), status=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            return self.handle_api_post(parsed.path, self.read_json())
        except ValueError as exc:
            self.send_error_json(str(exc), status=400)
        except PermissionError as exc:
            self.send_error_json(str(exc), status=403)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(str(exc), status=500)

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            return self.handle_api_patch(parsed.path, self.read_json())
        except ValueError as exc:
            self.send_error_json(str(exc), status=400)
        except PermissionError as exc:
            self.send_error_json(str(exc), status=403)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(str(exc), status=500)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            return self.handle_api_delete(parsed.path)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(str(exc), status=500)

    def serve_static(self, path):
        if path == "/":
            file_path = STATIC_DIR / "index.html"
        else:
            requested = path.lstrip("/")
            file_path = (STATIC_DIR / requested).resolve()
            if not str(file_path).startswith(str(STATIC_DIR.resolve())):
                return self.send_text("Forbidden", status=403)
        if not file_path.exists() or not file_path.is_file():
            return self.send_text("Not found", status=404)
        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        if file_path.suffix in {".html", ".css", ".js"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def handle_api_get(self, path, query):
        with connect_db() as conn:
            if path == "/api/session":
                return self.send_json({"user": self.current_user(conn), "roles": ROLE_LABELS})
            current_user = self.require_user(conn)
            if not current_user:
                return
            if path == "/api/bootstrap":
                return self.send_json(
                    {
                        "current_user": current_user,
                        "roles": ROLE_LABELS,
                        "stages": STAGES,
                        "categories": CATEGORIES,
                        "priorities": PRIORITIES,
                        "contact_types": CONTACT_TYPES,
                        "discovery_sectors": DISCOVERY_SECTORS,
                        "providers": settings_snapshot(conn),
                        "strategy": strategy_snapshot(conn),
                        "ai_control": ai_control_snapshot(conn),
                        "stats": stats(conn),
                    }
                )
            if path == "/api/info":
                return self.send_json({"info": info_snapshot(conn)})
            if path == "/api/settings":
                return self.send_json({"settings": settings_snapshot(conn)})
            if path == "/api/strategy":
                return self.send_json({"strategy": strategy_snapshot(conn)})
            if path == "/api/ai-control":
                return self.send_json({"ai_control": ai_control_snapshot(conn)})
            if path == "/api/users":
                if not self.require_super_admin(current_user):
                    return
                return self.send_json({"users": list_users(conn), "roles": ROLE_LABELS})
            if path == "/api/team":
                return self.send_json({"users": list_team_users(conn), "roles": ROLE_LABELS})
            if path == "/api/reminders":
                return self.send_json({"reminders": list_reminders(conn)})
            if path == "/api/stats":
                return self.send_json(stats(conn))
            if path == "/api/workbench":
                return self.send_json(sales_workbench(conn))
            if path == "/api/map":
                return self.send_json({"map": map_opportunities(conn)})
            if path == "/api/leads":
                return self.send_json({"leads": list_leads(conn, query)})
            if path == "/api/leads/trash":
                return self.send_json({"leads": list_deleted_leads(conn, query)})
            match = re.fullmatch(r"/api/leads/(\d+)", path)
            if match:
                lead = get_lead(conn, int(match.group(1)))
                if not lead:
                    return self.send_error_json("Lead non trovato", status=404)
                return self.send_json({"lead": lead})
            match = re.fullmatch(r"/api/leads/(\d+)/audit", path)
            if match:
                lead = get_lead(conn, int(match.group(1)))
                if not lead:
                    return self.send_error_json("Lead non trovato", status=404)
                return self.send_json({"audit": lead.get("assistant", {})})
            if path == "/api/export/leads.csv":
                return self.send_text(export_csv(conn), content_type="text/csv; charset=utf-8")
            if path == "/api/templates":
                rows = conn.execute("SELECT * FROM message_templates ORDER BY id").fetchall()
                return self.send_json({"templates": [to_dict(row) for row in rows]})
        return self.send_error_json("Endpoint non trovato", status=404)

    def handle_api_post(self, path, payload):
        with connect_db() as conn:
            if path == "/api/login":
                user = authenticate_user(conn, payload.get("email", ""), payload.get("password", ""))
                if not user:
                    return self.send_error_json("Email o password non validi", status=401)
                token, _expires = create_session(
                    conn,
                    user["id"],
                    self.headers.get("User-Agent", ""),
                    self.client_address[0] if self.client_address else "",
                )
                return self.send_json(
                    {"user": user},
                    headers={"Set-Cookie": self.session_cookie_header(token)},
                )
            if path == "/api/logout":
                raw_token = self.cookie_value(SESSION_COOKIE)
                if raw_token:
                    conn.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_hash(raw_token),))
                return self.send_json(
                    {"ok": True},
                    headers={"Set-Cookie": self.session_cookie_header("", max_age=0)},
                )
            current_user = self.require_user(conn)
            if not current_user:
                return
            if path == "/api/leads":
                lead_id = create_lead(conn, payload)
                lead = get_lead(conn, lead_id)
                return self.send_json({"lead": lead}, status=201)
            if path == "/api/users":
                user = create_user(conn, payload, current_user)
                return self.send_json({"user": user}, status=201)
            if path == "/api/settings":
                return self.send_json({"settings": save_settings(conn, payload)})
            if path == "/api/info":
                set_setting(conn, "assistant_knowledge", (payload.get("assistant_knowledge") or "").strip())
                return self.send_json({"info": info_snapshot(conn)})
            if path == "/api/strategy":
                return self.send_json({"strategy": save_strategy(conn, payload)})
            if path == "/api/ai-control":
                return self.send_json({"ai_control": save_ai_control(conn, payload)})
            if path in {"/api/assistant/chat", "/api/facundo/chat"}:
                return self.send_json(assistant_chat(conn, payload, current_user))
            if path == "/api/import/leads":
                rows = payload.get("rows", [])
                created = []
                for row in rows:
                    try:
                        lead_id = create_lead(conn, row)
                        created.append(lead_id)
                    except ValueError:
                        continue
                return self.send_json({"created": created, "count": len(created)}, status=201)
            if path == "/api/leads/bulk-delete":
                result = bulk_delete_leads(conn, payload)
                return self.send_json(result)
            if path == "/api/leads/bulk-restore":
                result = bulk_restore_leads(conn, payload)
                return self.send_json(result)
            if path == "/api/reminders":
                row = create_reminder(conn, payload, current_user)
                return self.send_json({"reminder": reminder_payload(row)}, status=201)
            if path == "/api/scan-url":
                scan = analyze_website(payload.get("url", ""))
                insert_scan(conn, None, scan)
                return self.send_json({"scan": scan}, status=201)
            if path == "/api/discovery/osm":
                result = discover_osm_leads(conn, payload)
                return self.send_json(result, status=201)
            if path == "/api/discovery/google":
                result = discover_google_leads(conn, payload)
                return self.send_json(result, status=201)
            if path == "/api/discovery/batch":
                result = discover_batch_leads(conn, payload)
                return self.send_json(result, status=201)

            match = re.fullmatch(r"/api/leads/(\d+)/contacts", path)
            if match:
                lead_id = int(match.group(1))
                stamp = now_iso()
                value = (payload.get("value") or "").strip()
                if not value:
                    raise ValueError("Contatto vuoto")
                cur = conn.execute(
                    """
                    INSERT INTO contacts (lead_id, type, value, label, is_primary, consent_status, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lead_id,
                        payload.get("type") if payload.get("type") in CONTACT_TYPES else "altro",
                        value,
                        (payload.get("label") or "").strip(),
                        int(bool(payload.get("is_primary"))),
                        (payload.get("consent_status") or "Da verificare").strip(),
                        (payload.get("notes") or "").strip(),
                        stamp,
                    ),
                )
                conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (stamp, lead_id))
                row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)).fetchone()
                return self.send_json({"contact": to_dict(row)}, status=201)

            match = re.fullmatch(r"/api/leads/(\d+)/activities", path)
            if match:
                lead_id = int(match.group(1))
                stamp = now_iso()
                kind = (payload.get("kind") or "note").strip()
                cur = conn.execute(
                    """
                    INSERT INTO activities (lead_id, kind, subject, body, channel, outcome, due_at, completed_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lead_id,
                        kind,
                        (payload.get("subject") or "").strip(),
                        (payload.get("body") or "").strip(),
                        (payload.get("channel") or "").strip(),
                        (payload.get("outcome") or "").strip(),
                        (payload.get("due_at") or "").strip(),
                        (payload.get("completed_at") or "").strip(),
                        stamp,
                    ),
                )
                if kind in {"email", "call", "dm", "whatsapp"}:
                    conn.execute("UPDATE leads SET last_contacted_at = ?, updated_at = ? WHERE id = ?", (stamp, stamp, lead_id))
                else:
                    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (stamp, lead_id))
                row = conn.execute("SELECT * FROM activities WHERE id = ?", (cur.lastrowid,)).fetchone()
                return self.send_json({"activity": to_dict(row)}, status=201)

            match = re.fullmatch(r"/api/leads/(\d+)/scan", path)
            if match:
                lead_id = int(match.group(1))
                lead = conn.execute("SELECT * FROM leads WHERE id = ? AND deleted_at IS NULL", (lead_id,)).fetchone()
                if not lead:
                    return self.send_error_json("Lead non trovato", status=404)
                target_url = payload.get("url") or lead["website"] or ""
                scan = analyze_website(target_url)
                insert_scan(conn, lead_id, scan)
                stamp = now_iso()
                conn.execute(
                    """
                    UPDATE leads
                    SET score = ?, category = ?, pain_points = ?, opportunity = ?, website = COALESCE(NULLIF(?, ''), website), updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        scan["score"],
                        scan["category_suggestion"],
                        ", ".join(scan["issues"]),
                        scan["opportunity"],
                        target_url,
                        stamp,
                        lead_id,
                    ),
                )
                for email in scan["emails"]:
                    exists = conn.execute(
                        "SELECT id FROM contacts WHERE lead_id = ? AND lower(value) = lower(?)",
                        (lead_id, email),
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            "INSERT INTO contacts (lead_id, type, value, label, consent_status, created_at) VALUES (?, 'email', ?, 'Dal sito', 'Da verificare', ?)",
                            (lead_id, email, stamp),
                        )
                for phone in scan["phones"]:
                    exists = conn.execute(
                        "SELECT id FROM contacts WHERE lead_id = ? AND value = ?",
                        (lead_id, phone),
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            "INSERT INTO contacts (lead_id, type, value, label, consent_status, created_at) VALUES (?, 'telefono', ?, 'Dal sito', 'Da verificare', ?)",
                            (lead_id, phone, stamp),
                        )
                return self.send_json({"scan": scan, "lead": get_lead(conn, lead_id)}, status=201)

            match = re.fullmatch(r"/api/leads/(\d+)/message", path)
            if match:
                message = build_message(conn, int(match.group(1)), payload)
                if not message:
                    return self.send_error_json("Lead non trovato", status=404)
                return self.send_json({"message": message})

            match = re.fullmatch(r"/api/leads/(\d+)/ai-score", path)
            if match:
                result = ai_score_lead(conn, int(match.group(1)))
                if not result:
                    return self.send_error_json("Lead non trovato", status=404)
                return self.send_json(result, status=201)

            match = re.fullmatch(r"/api/leads/(\d+)/research", path)
            if match:
                result = research_lead(conn, int(match.group(1)), payload)
                if not result:
                    return self.send_error_json("Lead non trovato", status=404)
                return self.send_json(result, status=201)
        return self.send_error_json("Endpoint non trovato", status=404)

    def handle_api_patch(self, path, payload):
        with connect_db() as conn:
            current_user = self.require_user(conn)
            if not current_user:
                return
            match = re.fullmatch(r"/api/users/(\d+)", path)
            if match:
                user = update_user(conn, int(match.group(1)), payload, current_user)
                if not user:
                    return self.send_error_json("Utente non trovato", status=404)
                return self.send_json({"user": user})
            if path == "/api/leads/bulk":
                result = bulk_update_leads(conn, payload)
                return self.send_json(result)
            match = re.fullmatch(r"/api/reminders/(\d+)", path)
            if match:
                row = update_reminder(conn, int(match.group(1)), payload, current_user)
                if not row:
                    return self.send_error_json("Promemoria non trovato", status=404)
                return self.send_json({"reminder": reminder_payload(row)})
            match = re.fullmatch(r"/api/leads/(\d+)", path)
            if not match:
                return self.send_error_json("Endpoint non trovato", status=404)
            lead_id = int(match.group(1))
            update_lead(conn, lead_id, payload)
            lead = get_lead(conn, lead_id)
            if not lead:
                return self.send_error_json("Lead non trovato", status=404)
            return self.send_json({"lead": lead})

    def handle_api_delete(self, path):
        with connect_db() as conn:
            current_user = self.require_user(conn)
            if not current_user:
                return
            match = re.fullmatch(r"/api/leads/(\d+)", path)
            if not match:
                return self.send_error_json("Endpoint non trovato", status=404)
            lead_id = int(match.group(1))
            conn.execute("UPDATE leads SET deleted_at = ?, updated_at = ? WHERE id = ?", (now_iso(), now_iso(), lead_id))
        return self.send_json({"ok": True})


def run_server(host, port, open_browser):
    init_db()
    server = ThreadingHTTPServer((host, port), CRMHandler)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{port}"
    print(f"CRM locale avviato: {url}")
    print(f"Database: {DB_PATH}")
    if host in {"0.0.0.0", "::"}:
        print("Accesso rete abilitato: usa HTTPS/proxy prima di esporlo pubblicamente.")
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCRM fermato.")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="CRM locale per lead e opportunita digitali")
    parser.add_argument("--host", default=os.environ.get("CRM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CRM_PORT", "8765")))
    parser.add_argument("--open", action="store_true", help="Apri il browser automaticamente")
    args = parser.parse_args()
    run_server(args.host, args.port, args.open)


if __name__ == "__main__":
    main()
