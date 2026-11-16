"""
Verspätungsbot – trackt, wie pünktlich Twitch-Streamer laut ihrem Streamplan live gehen.

Ablauf:
  1. Streamer aus streamers.txt laden und ihre Twitch-IDs holen
  2. Jede Stunde: Streampläne holen und in der Datenbank speichern
  3. Alle 2 Minuten: prüfen, wer live gegangen ist
  4. Neuer Stream -> passenden geplanten Termin suchen -> Verspätung berechnen & speichern
"""
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------- Einstellungen
load_dotenv()
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

DB_PFAD = os.getenv("DB_PATH", "verspaetung.db")
STREAMER_DATEI = "streamers.txt"

LIVE_INTERVALL = 120            # Sekunden zwischen zwei Live-Checks
PLAN_INTERVALL = 60 * 60        # Sekunden zwischen zwei Streamplan-Updates
MAX_ZU_SPAET = timedelta(hours=6)   # Termin darf so weit VOR dem echten Start liegen
MAX_ZU_FRUEH = timedelta(hours=2)   # Termin darf so weit NACH dem echten Start liegen

API = "https://api.twitch.tv/helix"
BERLIN = ZoneInfo("Europe/Berlin")
ZEITFORMAT = "%Y-%m-%dT%H:%M:%SZ"   # gleiches Format wie Twitch (UTC)


# ---------------------------------------------------------------- Hilfsfunktionen
def jetzt():
    return datetime.now(timezone.utc)


def parse_zeit(text):
    """Twitch-Zeitstempel ('2026-11-16T17:00:00Z') -> datetime in UTC."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def als_text(dt):
    return dt.astimezone(timezone.utc).strftime(ZEITFORMAT)


def berlin(dt):
    return dt.astimezone(BERLIN).strftime("%d.%m. %H:%M")


def log(nachricht):
    print(f"[{datetime.now(BERLIN).strftime('%d.%m. %H:%M:%S')}] {nachricht}", flush=True)


def in_bloecken(liste, groesse=100):
    """Twitch erlaubt max. 100 IDs pro Anfrage -> Liste aufteilen."""
    for i in range(0, len(liste), groesse):
        yield liste[i:i + groesse]


# ---------------------------------------------------------------- Twitch-API
_token = None
_token_ablauf = datetime.min.replace(tzinfo=timezone.utc)


def hole_token():
    """App-Access-Token per Client-Credentials-Flow holen."""
    global _token, _token_ablauf
    r = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }, timeout=10)
    r.raise_for_status()
    daten = r.json()
    _token = daten["access_token"]
    # 5 Minuten Puffer, damit das Token nicht mitten in einer Anfrage abläuft
    _token_ablauf = jetzt() + timedelta(seconds=daten["expires_in"] - 300)
    log("Neues Twitch-Token geholt.")


def twitch_get(pfad, params):
    """GET-Anfrage an die Twitch-API, erneuert das Token bei Bedarf automatisch."""
    if _token is None or jetzt() >= _token_ablauf:
        hole_token()
    for _ in range(2):
        r = requests.get(f"{API}/{pfad}", params=params, timeout=10, headers={
            "Client-Id": CLIENT_ID,
            "Authorization": f"Bearer {_token}",
        })
        if r.status_code != 401:
            return r
        hole_token()   # Token ungültig -> neu holen und nochmal versuchen
    return r


# ---------------------------------------------------------------- Datenbank
def init_db():
    db = sqlite3.connect(DB_PFAD)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS streamer (
            id     TEXT PRIMARY KEY,   -- Twitch-User-ID
            login  TEXT NOT NULL,      -- z. B. papaplatte
            name   TEXT NOT NULL       -- z. B. Papaplatte
        );
        CREATE TABLE IF NOT EXISTS termine (
            id          TEXT PRIMARY KEY,   -- Segment-ID aus dem Twitch-Streamplan
            streamer_id TEXT NOT NULL,
            start       TEXT NOT NULL,      -- geplanter Start (UTC)
            titel       TEXT,
            abgesagt    INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS streams (
            stream_id       TEXT PRIMARY KEY,
            streamer_id     TEXT NOT NULL,
            gestartet       TEXT NOT NULL,  -- echter Start (UTC)
            termin_id       TEXT,           -- NULL = kein passender Termin
            geplant         TEXT,           -- geplanter Start (UTC)
            verspaetung_min INTEGER         -- negativ = zu früh
        );
    """)
    db.commit()
    return db


# ---------------------------------------------------------------- 1. Streamer laden
def lade_streamer(db):
    with open(STREAMER_DATEI, encoding="utf-8") as f:
        logins = [z.strip().lower() for z in f
                  if z.strip() and not z.strip().startswith("#")]

    streamer = {}   # id -> Anzeigename
    for block in in_bloecken(logins):
        r = twitch_get("users", [("login", l) for l in block])
        r.raise_for_status()
        for u in r.json()["data"]:
            streamer[u["id"]] = u["display_name"]
            db.execute("INSERT OR REPLACE INTO streamer VALUES (?, ?, ?)",
                       (u["id"], u["login"], u["display_name"]))
    db.commit()

    gefunden = {n.lower() for n in streamer.values()}
    for l in logins:
        if l not in gefunden:
            log(f"WARNUNG: Streamer '{l}' gibt es auf Twitch nicht – Tippfehler?")
    log(f"{len(streamer)} Streamer geladen.")
    return streamer


# ---------------------------------------------------------------- 2. Streampläne
def aktualisiere_plaene(db, streamer):
    # Ab gestern abfragen, damit auch heutige (schon vergangene) Termine dabei sind
    ab = als_text(jetzt() - timedelta(days=1))
    anzahl = 0
    for sid, name in streamer.items():
        r = twitch_get("schedule", {"broadcaster_id": sid, "start_time": ab, "first": 25})
        if r.status_code == 404:          # kein Streamplan hinterlegt
            continue
        r.raise_for_status()
        for seg in r.json()["data"]["segments"] or []:   # None im Urlaubsmodus
            db.execute("""
                INSERT INTO termine (id, streamer_id, start, titel, abgesagt)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    start = excluded.start, titel = excluded.titel, abgesagt = excluded.abgesagt
            """, (seg["id"], sid, seg["start_time"], seg["title"],
                  1 if seg.get("canceled_until") else 0))
            anzahl += 1
    db.commit()
    log(f"Streampläne aktualisiert ({anzahl} Termine).")


# ---------------------------------------------------------------- 3. Live-Check
def finde_termin(db, streamer_id, gestartet):
    """Den geplanten Termin suchen, der am nächsten am echten Start liegt."""
    kandidaten = db.execute("""
        SELECT id, start FROM termine
        WHERE streamer_id = ? AND abgesagt = 0 AND start BETWEEN ? AND ?
    """, (streamer_id,
          als_text(gestartet - MAX_ZU_SPAET),
          als_text(gestartet + MAX_ZU_FRUEH))).fetchall()
    if not kandidaten:
        return None
    return min(kandidaten, key=lambda t: abs(gestartet - parse_zeit(t[1])))


def neuer_stream(db, stream):
    sid = stream["user_id"]
    gestartet = parse_zeit(stream["started_at"])
    termin = finde_termin(db, sid, gestartet)

    # Wurde dieser Termin schon einem Stream zugeordnet? -> Stream-Neustart, nicht doppelt zählen
    if termin and db.execute("SELECT 1 FROM streams WHERE termin_id = ?", (termin[0],)).fetchone():
        log(f"{stream['user_name']}: Neustart erkannt – wird nicht gewertet.")
        termin = None

    if termin:
        geplant = parse_zeit(termin[1])
        minuten = round((gestartet - geplant).total_seconds() / 60)
        text = f"{minuten} Min. zu spät" if minuten > 0 else f"{-minuten} Min. zu früh"
        log(f"{stream['user_name']} ist live! Geplant {berlin(geplant)}, "
            f"gestartet {berlin(gestartet)} -> {text}")
        werte = (termin[0], termin[1], minuten)
    else:
        log(f"{stream['user_name']} ist live (seit {berlin(gestartet)}), aber ohne passenden Termin.")
        werte = (None, None, None)

    db.execute("INSERT INTO streams VALUES (?, ?, ?, ?, ?, ?)",
               (stream["id"], sid, stream["started_at"], *werte))
    db.commit()


def pruefe_live(db, streamer):
    for block in in_bloecken(list(streamer)):
        r = twitch_get("streams", [("user_id", i) for i in block] + [("first", 100)])
        r.raise_for_status()
        for stream in r.json()["data"]:
            schon_bekannt = db.execute("SELECT 1 FROM streams WHERE stream_id = ?",
                                       (stream["id"],)).fetchone()
            if not schon_bekannt:
                neuer_stream(db, stream)


# ---------------------------------------------------------------- Hauptschleife
def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise SystemExit("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET fehlen in der .env!")

    db = init_db()
    streamer = lade_streamer(db)
    letztes_plan_update = 0.0

    log("Bot läuft. Beenden mit Strg+C.")
    while True:
        try:
            if time.time() - letztes_plan_update > PLAN_INTERVALL:
                aktualisiere_plaene(db, streamer)
                letztes_plan_update = time.time()
            pruefe_live(db, streamer)
        except requests.RequestException as fehler:
            # Netzwerk-/API-Fehler sollen den Bot nicht beenden
            log(f"Fehler bei der Twitch-Abfrage: {fehler}")
        time.sleep(LIVE_INTERVALL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Bot beendet.")
