"""
Webseite für den Verspätungsbot.
Liest dieselbe SQLite-Datenbank wie bot.py und stellt sie als Webseite + JSON-API bereit.

Starten (lokal):  py -m uvicorn web:app --reload
Dann im Browser:  http://localhost:8000
"""
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
DB_PFAD = os.getenv("DB_PATH", "verspaetung.db")
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="AZB Streamer")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def db():
    verbindung = sqlite3.connect(DB_PFAD)
    verbindung.row_factory = sqlite3.Row   # Zeilen als Dictionary statt Tupel
    return verbindung


# ---------------------------------------------------------------- Seiten
@app.get("/")
def startseite():
    return FileResponse(STATIC / "index.html")


@app.get("/streamer/{login}")
def streamer_seite(login: str):
    return FileResponse(STATIC / "streamer.html")


# ---------------------------------------------------------------- API
@app.get("/api/rangliste")
def rangliste():
    with db() as con:
        zeilen = con.execute("""
            SELECT s.login, s.name,
                   COUNT(st.stream_id)                         AS streams,
                   COUNT(st.verspaetung_min)                   AS gewertet,
                   ROUND(AVG(st.verspaetung_min), 1)           AS schnitt,
                   MAX(st.verspaetung_min)                     AS rekord,
                   ROUND(100.0 * SUM(st.verspaetung_min <= 5)
                         / COUNT(st.verspaetung_min))          AS puenktlich,
                   MAX(st.gestartet)                           AS letzter_stream
            FROM streamer s
            LEFT JOIN streams st ON st.streamer_id = s.id
            GROUP BY s.id
            ORDER BY schnitt IS NULL, schnitt DESC
        """).fetchall()
    return [dict(z) for z in zeilen]


@app.get("/api/streamer/{login}")
def streamer_details(login: str):
    with db() as con:
        s = con.execute("SELECT id, login, name FROM streamer WHERE login = ?",
                        (login.lower(),)).fetchone()
        if s is None:
            raise HTTPException(404, "Streamer nicht gefunden")

        stats = con.execute("""
            SELECT COUNT(stream_id)                AS streams,
                   COUNT(verspaetung_min)          AS gewertet,
                   ROUND(AVG(verspaetung_min), 1)  AS schnitt,
                   MAX(verspaetung_min)            AS rekord,
                   MIN(verspaetung_min)            AS fruehester,
                   ROUND(100.0 * SUM(verspaetung_min <= 5) / COUNT(verspaetung_min)) AS puenktlich
            FROM streams WHERE streamer_id = ?
        """, (s["id"],)).fetchone()

        streams = con.execute("""
            SELECT gestartet, geplant, verspaetung_min
            FROM streams WHERE streamer_id = ?
            ORDER BY gestartet DESC LIMIT 50
        """, (s["id"],)).fetchall()

        naechste = con.execute("""
            SELECT start, titel FROM termine
            WHERE streamer_id = ? AND abgesagt = 0 AND start > strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            ORDER BY start LIMIT 5
        """, (s["id"],)).fetchall()

    return {
        "login": s["login"],
        "name": s["name"],
        "stats": dict(stats),
        "streams": [dict(z) for z in streams],
        "naechste_termine": [dict(z) for z in naechste],
    }
