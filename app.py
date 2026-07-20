from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import re
import secrets
import sqlite3
import unicodedata


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
PASSWORD = "1961"
SESSION_TOKEN = secrets.token_urlsafe(32)


FIELDS = [
    "nev",
    "azonosito_szam",
    "adoszam",
    "allando_lakcim",
    "iranyitoszam",
    "megye",
    "varos",
    "kozterulet_neve",
    "kozterulet_jellege",
    "kozterulet_szama",
    "emelet",
    "ajtoszam",
    "cefre_atveteli_azonosito",
    "fozes_start",
    "fozes_end",
    "kezdo",
    "zaro",
    "szesz_foka",
    "mennyiseg_literben",
    "hektoliterfokban",
    "kiadas_datuma",
    "nyugtaertek",
]


def clean_year(value):
    year = int(value)
    if year < 2000 or year > 2100:
        raise ValueError("Bad year")
    return year


def year_from_date(value):
    match = re.match(r"^(\d{4})-\d{2}-\d{2}$", str(value or ""))
    if not match:
        return None
    return clean_year(match.group(1))


def db_path(year):
    return DATA / f"palinka_{year}.db"


def table_name(year):
    return f"clients_{year}"


def connect_year(year):
    year = clean_year(year)
    conn = sqlite3.connect(db_path(year))
    conn.row_factory = sqlite3.Row
    table = table_name(year)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nev TEXT NOT NULL,
            azonosito_szam TEXT NOT NULL,
            adoszam TEXT NOT NULL,
            allando_lakcim TEXT NOT NULL,
            iranyitoszam TEXT NOT NULL DEFAULT '',
            megye TEXT NOT NULL DEFAULT '',
            varos TEXT NOT NULL DEFAULT '',
            kozterulet_neve TEXT NOT NULL DEFAULT '',
            kozterulet_jellege TEXT NOT NULL DEFAULT '',
            kozterulet_szama TEXT NOT NULL DEFAULT '',
            emelet TEXT NOT NULL DEFAULT '',
            ajtoszam TEXT NOT NULL DEFAULT '',
            cefre_atveteli_azonosito TEXT NOT NULL,
            fozes_start TEXT NOT NULL,
            fozes_end TEXT NOT NULL,
            kezdo REAL NOT NULL,
            zaro REAL NOT NULL,
            szesz_foka REAL NOT NULL,
            mennyiseg_literben REAL NOT NULL,
            hektoliterfokban REAL NOT NULL,
            kiadas_datuma TEXT NOT NULL,
            nyugtaertek REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    migrations = {
        "iranyitoszam": "TEXT NOT NULL DEFAULT ''",
        "megye": "TEXT NOT NULL DEFAULT ''",
        "varos": "TEXT NOT NULL DEFAULT ''",
        "kozterulet_neve": "TEXT NOT NULL DEFAULT ''",
        "kozterulet_jellege": "TEXT NOT NULL DEFAULT ''",
        "kozterulet_szama": "TEXT NOT NULL DEFAULT ''",
        "emelet": "TEXT NOT NULL DEFAULT ''",
        "ajtoszam": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in migrations.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()
    return conn, table


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def strip_accents(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char))


def compact_key(value):
    text = strip_accents(value).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def tax_key(value):
    return compact_key(value)


def build_address(data):
    parts = [
        data.get("iranyitoszam", ""),
        data.get("megye", ""),
        data.get("varos", ""),
        data.get("kozterulet_neve", ""),
        data.get("kozterulet_jellege", ""),
        data.get("kozterulet_szama", ""),
    ]
    if data.get("emelet"):
        parts.append(f"{data['emelet']} emelet")
    if data.get("ajtoszam"):
        parts.append(f"{data['ajtoszam']} ajtó")
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def value_for(data, key):
    if hasattr(data, "get"):
        return data.get(key, "")
    try:
        return data[key]
    except (KeyError, IndexError):
        return ""


def address_compare_text(data):
    structured = [
        value_for(data, "iranyitoszam"),
        value_for(data, "megye"),
        value_for(data, "varos"),
        value_for(data, "kozterulet_neve"),
        value_for(data, "kozterulet_jellege"),
        value_for(data, "kozterulet_szama"),
        value_for(data, "emelet"),
        value_for(data, "ajtoszam"),
    ]
    if any(str(part).strip() for part in structured):
        return " ".join(str(part).strip() for part in structured if str(part).strip())
    return str(value_for(data, "allando_lakcim"))


def compute_values(payload):
    data = {field: payload.get(field, "") for field in FIELDS}
    for field in [
        "nev",
        "azonosito_szam",
        "adoszam",
        "iranyitoszam",
        "megye",
        "varos",
        "kozterulet_neve",
        "kozterulet_jellege",
        "kozterulet_szama",
        "cefre_atveteli_azonosito",
        "fozes_start",
        "fozes_end",
        "kiadas_datuma",
    ]:
        data[field] = str(data[field]).strip()
    for field in ["allando_lakcim", "emelet", "ajtoszam"]:
        data[field] = str(data.get(field, "")).strip()
    data["allando_lakcim"] = build_address(data)

    kezdo = float(payload.get("kezdo") or 0)
    zaro = float(payload.get("zaro") or 0)
    szesz = float(payload.get("szesz_foka") or 0)
    if zaro < kezdo:
        raise ValueError("Záró óraállás cannot be smaller than kezdő óraállás.")
    if szesz < 0:
        raise ValueError("Szesz foka cannot be negative.")

    liter = round(zaro - kezdo, 3)
    hektoliter = round((liter * szesz) / 100, 1)
    nyugta = round(hektoliter * 1400, 0)
    data.update(
        {
            "kezdo": kezdo,
            "zaro": zaro,
            "szesz_foka": szesz,
            "mennyiseg_literben": liter,
            "hektoliterfokban": hektoliter,
            "nyugtaertek": nyugta,
        }
    )
    return data


def warnings_for(conn, table, data, current_id=None):
    warnings = []
    params = []
    where = ""
    if current_id:
        where = "WHERE id != ?"
        params.append(current_id)
    rows = conn.execute(f"SELECT * FROM {table} {where}", params).fetchall()
    matches = []
    for row in rows:
        same = []
        if compact_key(row["nev"]) == compact_key(data["nev"]):
            same.append("Név")
        if tax_key(row["adoszam"]) == tax_key(data["adoszam"]) and tax_key(data["adoszam"]):
            same.append("Adószám")
        row_address = address_compare_text(row)
        new_address = address_compare_text(data)
        if compact_key(row_address) == compact_key(new_address):
            same.append("Lakcím")
        if len(same) >= 2:
            matches.append({"id": row["id"], "nev": row["nev"], "same": same})
    if matches:
        warnings.append(
            {
                "type": "possible_existing_client",
                "message": "Legalább két adat egyezik egy meglévő bejegyzéssel ebben az évben.",
                "matches": matches,
            }
        )
    if data["hektoliterfokban"] >= 43:
        warnings.append(
            {
                "type": "high_hektoliter",
                "message": "A hektoliterfok 43 vagy több.",
                "value": data["hektoliterfokban"],
            }
        )
    return warnings


def totals(conn, table):
    row = conn.execute(
        f"SELECT COALESCE(SUM(hektoliterfokban), 0) AS hektoliter, COALESCE(SUM(nyugtaertek), 0) AS nyugta FROM {table}"
    ).fetchone()
    return {"hektoliterfokban": round(row["hektoliter"], 1), "nyugtaertek": round(row["nyugta"], 0)}


def id_number_key(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    return int(digits) if digits else 0


def sorted_rows(rows, order):
    if order == "name":
        return sorted(rows, key=lambda row: compact_key(row["nev"]))
    if order == "azonosito":
        return sorted(rows, key=lambda row: (id_number_key(row["azonosito_szam"]), compact_key(row["azonosito_szam"])))
    if order == "kiadas":
        return sorted(rows, key=lambda row: (row["kiadas_datuma"], row["id"]))
    return rows


def known_years():
    found = []
    for file in DATA.glob("palinka_*.db"):
        match = re.match(r"palinka_(\d{4})\.db", file.name)
        if match:
            found.append(int(match.group(1)))
    current = 2026
    years = sorted(set(found + [current]), reverse=True)
    return years


class Handler(BaseHTTPRequestHandler):
    def is_logged_in(self):
        cookie = self.headers.get("Cookie", "")
        return f"palinka_auth={SESSION_TOKEN}" in cookie

    def redirect_login(self):
        self.send_response(302)
        self.send_header("Location", "/login.html")
        self.end_headers()

    def send_json(self, status, body):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        public_login_files = {"/login.html", "/styles.css"}
        if parsed.path not in public_login_files and not self.is_logged_in():
            if parsed.path.startswith("/api/"):
                return self.send_json(401, {"error": "Jelszó kell."})
            return self.redirect_login()
        if parsed.path == "/login.html" and self.is_logged_in():
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed)
            return
        target = PUBLIC / ("index.html" if parsed.path == "/" else parsed.path.lstrip("/"))
        if not target.resolve().is_relative_to(PUBLIC.resolve()) or not target.exists():
            self.send_error(404)
            return
        content_type = "text/html; charset=utf-8"
        if target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        if target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_api_get(self, parsed):
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/years":
                return self.send_json(200, {"years": known_years()})
            year = clean_year(query.get("year", [known_years()[0]])[0])
            conn, table = connect_year(year)
            if parsed.path == "/api/records":
                order = query.get("order", ["kiadas"])[0]
                rows = conn.execute(f"SELECT * FROM {table} ORDER BY fozes_start DESC, id DESC").fetchall()
                rows = sorted_rows(rows, order)
                body = {"records": [row_to_dict(row) for row in rows], "totals": totals(conn, table)}
                conn.close()
                return self.send_json(200, body)
            if parsed.path == "/api/people":
                rows = conn.execute(f"SELECT DISTINCT nev FROM {table} ORDER BY nev COLLATE NOCASE").fetchall()
                body = {"people": [row["nev"] for row in rows]}
                conn.close()
                return self.send_json(200, body)
            if parsed.path == "/api/person":
                name = query.get("nev", [""])[0]
                rows = conn.execute(f"SELECT * FROM {table} WHERE nev = ? ORDER BY fozes_start DESC, id DESC", [name]).fetchall()
                body = {"records": [row_to_dict(row) for row in rows], "totals": totals(conn, table)}
                conn.close()
                return self.send_json(200, body)
            self.send_error(404)
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})

    def do_POST(self):
        if self.path == "/api/login":
            try:
                payload = self.read_json()
                if str(payload.get("password", "")) != PASSWORD:
                    return self.send_json(401, {"error": "Rossz jelszó."})
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"palinka_auth={SESSION_TOKEN}; HttpOnly; SameSite=Lax; Path=/")
                body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except Exception as exc:
                return self.send_json(400, {"error": str(exc)})
        if not self.is_logged_in():
            return self.send_json(401, {"error": "Jelszó kell."})
        if self.path != "/api/records":
            self.send_error(404)
            return
        try:
            payload = self.read_json()
            force = bool(payload.get("force"))
            data = compute_values(payload)
            year = year_from_date(data["kiadas_datuma"]) or clean_year(payload.get("year"))
            conn, table = connect_year(year)
            warnings = warnings_for(conn, table, data)
            if warnings and not force:
                conn.close()
                return self.send_json(409, {"warnings": warnings, "calculated": data})
            placeholders = ", ".join(["?"] * len(FIELDS))
            columns = ", ".join(FIELDS)
            conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", [data[field] for field in FIELDS])
            conn.commit()
            body = {"ok": True, "totals": totals(conn, table)}
            conn.close()
            body["year"] = year
            return self.send_json(201, body)
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})

    def do_PUT(self):
        if not self.is_logged_in():
            return self.send_json(401, {"error": "Jelszó kell."})
        match = re.match(r"^/api/records/(\d+)$", self.path)
        if not match:
            self.send_error(404)
            return
        try:
            record_id = int(match.group(1))
            payload = self.read_json()
            year = clean_year(payload.get("year"))
            force = bool(payload.get("force"))
            data = compute_values(payload)
            conn, table = connect_year(year)
            warnings = warnings_for(conn, table, data, current_id=record_id)
            if warnings and not force:
                conn.close()
                return self.send_json(409, {"warnings": warnings, "calculated": data})
            assignments = ", ".join([f"{field} = ?" for field in FIELDS])
            conn.execute(
                f"UPDATE {table} SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                [data[field] for field in FIELDS] + [record_id],
            )
            conn.commit()
            body = {"ok": True, "totals": totals(conn, table)}
            conn.close()
            return self.send_json(200, body)
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})

    def do_DELETE(self):
        if not self.is_logged_in():
            return self.send_json(401, {"error": "Jelszó kell."})
        parsed = urlparse(self.path)
        match = re.match(r"^/api/records/(\d+)$", parsed.path)
        if not match:
            self.send_error(404)
            return
        try:
            record_id = int(match.group(1))
            query = parse_qs(parsed.query)
            year = clean_year(query.get("year", [None])[0])
            conn, table = connect_year(year)
            conn.execute(f"DELETE FROM {table} WHERE id = ?", [record_id])
            conn.commit()
            body = {"ok": True, "totals": totals(conn, table)}
            conn.close()
            return self.send_json(200, body)
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    default_host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    host = os.environ.get("HOST", default_host)
    port = int(os.environ.get("PORT", "5177"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Pálinka client database running at http://{host}:{port}")
    server.serve_forever()
