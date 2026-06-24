import os
import re
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

# Q-kodord → Notion databas-ID
Q_DATABASES = {
    "notion":     "a3bebc3f85f14063b007905ed851da64",
    "claude":     "8fb5af2d958f4792b14f0846fe271b3b",
    "brainstorm": "6640fad4648442c98372a8dc9052a22b",
    "zenter":     "4d1a88b046434b5aba9bdef6c503df17",
    "privat":     "df00e290a0dc43d19891a181c8ff47e8",
}

FALLBACK_DATABASE = Q_DATABASES["notion"]

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def find_q_destination(text: str) -> tuple[str, str]:
    """
    Letar efter 'Q <destination>' i texten (case-insensitivt).
    Returnerar (databas_id, källa) där källa är kodordet eller 'fallback'.
    """
    pattern = r"\bq\s+(" + "|".join(Q_DATABASES.keys()) + r")\b"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        destination = match.group(1).lower()
        return Q_DATABASES[destination], f"Q {destination.capitalize()}"
    return FALLBACK_DATABASE, "fallback"


def add_to_notion(database_id: str, summary: str, source: str) -> dict:
    """Skapar en ny post i Notion-databasen."""
    url = "https://api.notion.com/v1/pages"
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {
                "title": [{"text": {"content": title[:100]}}]
            },
            "Sammanfattning": {
                "rich_text": [{"text": {"content": summary}}]
            },
            "Datum": {
                "date": {"start": now}
            },
            "Källa": {
                "rich_text": [{"text": {"content": source}}]
            },
        },
    }

    response = requests.post(url, headers=NOTION_HEADERS, json=payload)
    response.raise_for_status()
    return response.json()


@app.route("/webhook", methods=["POST"])
def webhook():
    # Verifiera webhook-token
    token = request.headers.get("X-Webhook-Secret") or request.args.get("secret")
    if WEBHOOK_SECRET and token != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}

    # Omi Memory Creation Trigger skickar structured.overview som sammanfattning
    # och transcript som råtext. Vi tar overview i första hand.
    structured = data.get("structured") or {}
    summary = (
        structured.get("overview")
        or data.get("summary")
        or data.get("text")
        or data.get("transcript")
        or ""
    )

    # Titeln från Omi (structured.title) används som namn om den finns
    title = structured.get("title") or summary[:100]

    if not summary:
        return jsonify({"error": "No summary found in payload"}), 400

    database_id, source = find_q_destination(summary)

    try:
        notion_response = add_to_notion(database_id, summary, source)
        return jsonify({
            "status": "ok",
            "notion_page_id": notion_response.get("id"),
            "destination": source,
        }), 200
    except requests.HTTPEr