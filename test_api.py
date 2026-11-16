import os
import requests
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# 1) App-Access-Token holen
token = requests.post("https://id.twitch.tv/oauth2/token", params={
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "grant_type": "client_credentials",
}).json()["access_token"]

headers = {"Client-Id": CLIENT_ID, "Authorization": f"Bearer {token}"}

# 2) Streamer-Name → User-ID
streamer = "papaplatte"   # beliebigen Namen eintragen
user = requests.get("https://api.twitch.tv/helix/users",
                    headers=headers, params={"login": streamer}).json()["data"][0]
print(f"{user['display_name']} hat die ID {user['id']}")

# 3) Streamplan abfragen
r = requests.get("https://api.twitch.tv/helix/schedule",
                 headers=headers, params={"broadcaster_id": user["id"]})
if r.status_code == 404:
    print("Kein Streamplan hinterlegt.")
else:
    for seg in r.json()["data"]["segments"][:5]:
        print("Geplant:", seg["start_time"], "-", seg["title"])

# 4) Ist er gerade live?
live = requests.get("https://api.twitch.tv/helix/streams",
                    headers=headers, params={"user_id": user["id"]}).json()["data"]
print("LIVE seit", live[0]["started_at"] if live else "– gerade offline")