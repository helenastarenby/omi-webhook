import os
import re
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

Q_DATABASES = {
    "notion":     "a3bebc3f85f14063b007905ed851da64",
    "claude":     "8fb5af2d958f4792b14f0846fe271b3b",
    "brainstorm": "6640fad4648442c98372a8dc9052a22b",
    "zenter":     "4d1a88b046434b5aba9bdef6c503df17",
    "privat":     "df00e290a0dc43d19891a181c8ff47e8",
}

FALLBACK_DATABASE = Q_DATABASES["notion"]

TRIGGERS = [
    (r"spara\s+analys",     "claude"),
    (r"spara\s+privat",     "privat"),
    (r"spara\s+brainstorm", "brainstorm"),
    (r"spara\s+zenter",     "zenter"),
    (r"\bq\s+claude\b",     "claude"),
    (r"\bq\s+brainstorm\b", "brainstorm"),
    (r"\bq\s+zenter\b",     "zenter"),
    (r"\bq\s+privat\b",     "privat"),
    (r"\bq\s+notion\b",     "notion"),
]


def get_notion_headers():
    return {
        "Authorization": "Bearer " + os.environ.get("NOTION_API_KEY", ""),
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def find_q_destination(text):
    for pattern, destination in TRIGGERS:
        if re.search(pattern, text, re.IGNORECASE):
            return Q_DATABASES[destination], destination.capitalize()
    return FALLBACK_DATABASE, "notion"


def add_to_notion(database_id, title, summary, source):
    url = "https://api.notion.com/v1/pages"
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Namn": {"title": [{"text": {"content": title[:100]}}]},
            "Sammanfattning": {"rich_text": [{"text": {"content": summary}}]},
            "Datum": {"date": {"start": now}},
            "Kalla": {"rich_text": [{"text": {"content": source}}]},
        },
    }
    response = requests.post(url, headers=get_notion_headers(), json=payload)
    response.raise_for_status()
    return response.json()


@app.route("/webhook", methods=["POST"])
def webhook():
    token = request.headers.get("X-Webhook-Secret") or request.args.get("secret")
    if WEBHOOK_SECRET and token != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    structured = data.get("structured") or {}
    summary = (
        structured.get("overview")
        or data.get("summary")
        or data.get("text")
        or data.get("transcript")
        or ""
    )
    title = structured.get("title") or summary[:100]

    if not summary:
        return jsonify({"error": "No summary found in payload"}), 400

    database_id, source = find_q_destination(summary)

    try:
        notion_response = add_to_notion(database_id, title, summary, source)
        return jsonify({
            "status": "ok",
            "notion_page_id": notion_response.get("id"),
            "destination": source,
        }), 200
    except requests.HTTPError as e:
        return jsonify({"error": str(e), "details": e.response.text}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
