"""Zeigt die aktuelle Verspätungs-Rangliste aus der Datenbank im Terminal an."""
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()
db = sqlite3.connect(os.getenv("DB_PATH", "verspaetung.db"))

zeilen = db.execute("""
    SELECT s.name,
           COUNT(*)                                          AS streams,
           ROUND(AVG(st.verspaetung_min), 1)                 AS schnitt,
           MAX(st.verspaetung_min)                           AS rekord,
           ROUND(100.0 * SUM(st.verspaetung_min <= 5) / COUNT(*)) AS puenktlich
    FROM streams st
    JOIN streamer s ON s.id = st.streamer_id
    WHERE st.verspaetung_min IS NOT NULL
    GROUP BY s.id
    ORDER BY schnitt DESC
""").fetchall()

if not zeilen:
    print("Noch keine gewerteten Streams. Lass den Bot eine Weile laufen!")
else:
    print(f"{'#':>2}  {'Streamer':<20}{'Streams':>8}{'Ø Min.':>9}{'Rekord':>8}{'Pünktlich':>11}")
    print("-" * 60)
    for platz, (name, anzahl, schnitt, rekord, quote) in enumerate(zeilen, 1):
        print(f"{platz:>2}  {name:<20}{anzahl:>8}{schnitt:>9}{rekord:>8}{quote:>10.0f}%")
    print("\nPünktlich = höchstens 5 Minuten nach dem geplanten Start. Negative Werte = zu früh.")
