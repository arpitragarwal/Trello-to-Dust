import os
import requests
import json
from datetime import datetime

def _require_env(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value

# --- Configuration ---
TRELLO_API_KEY  = _require_env("TRELLO_API_KEY")
TRELLO_TOKEN    = _require_env("TRELLO_TOKEN")
TRELLO_BOARD_ID = "6a08b44123aa7d0d9e183f2d"

DUST_API_KEY       = _require_env("DUST_API_KEY")
DUST_WORKSPACE_ID  = "y2COuCuMBs"
DUST_SPACE_ID      = "vlt_cYuQaFeiw6KsL"
DUST_DATASOURCE_ID = "dts_W10jrplO6YA2g"

DUST_BASE_URL = f"https://dust.tt/api/v1/w/{DUST_WORKSPACE_ID}/spaces/{DUST_SPACE_ID}/data_sources/{DUST_DATASOURCE_ID}/documents"

# --- Step 1: Fetch all lists from the Trello board ---
def get_trello_lists():
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/lists"
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return {lst["id"]: lst["name"] for lst in response.json()}

# --- Step 2: Fetch all cards from the Trello board ---
def get_trello_cards():
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/cards"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "fields": "id,name,desc,url,idList,labels,due,dateLastActivity,address,locationName,coordinates",
        "checklists": "all",
        "members": "true",
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

# --- Step 3: Format a card as text for Dust ---
def format_card_text(card, list_name):
    lines = [
        f"# {card['name']}",
        f"**List:** {list_name}",
        f"**URL:** {card.get('url', 'N/A')}",
        f"**Due Date:** {card.get('due') or 'None'}",
        f"**Last Activity:** {card.get('dateLastActivity', 'N/A')}",
    ]

    labels = [lbl["name"] for lbl in card.get("labels", []) if lbl.get("name")]
    if labels:
        lines.append(f"**Labels:** {', '.join(labels)}")

    location_parts = []
    if card.get("locationName"):
        location_parts.append(card["locationName"])
    if card.get("address"):
        location_parts.append(card["address"])
    coords = card.get("coordinates")
    if coords:
        if isinstance(coords, dict):
            location_parts.append(f"({coords.get('latitude')}, {coords.get('longitude')})")
        else:
            location_parts.append(str(coords))
    if location_parts:
        lines.append(f"**Location:** {' — '.join(location_parts)}")

    if card.get("desc"):
        lines.append(f"\n## Description\n{card['desc']}")

    checklists = card.get("checklists", [])
    for checklist in checklists:
        lines.append(f"\n## Checklist: {checklist['name']}")
        for item in checklist.get("checkItems", []):
            status = "✅" if item["state"] == "complete" else "☐"
            lines.append(f"  {status} {item['name']}")

    return "\n".join(lines)

# --- Step 4: Upsert a card as a document into Dust ---
def upsert_to_dust(card_id, title, text, source_url, timestamp):
    url = f"{DUST_BASE_URL}/{card_id}"
    headers = {
        "Authorization": f"Bearer {DUST_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "title": title,
        "text": text,
        "source_url": source_url,
        "timestamp": int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() * 1000),
        "tags": ["trello"],
        "light_document_output": True,
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# --- Main sync function ---
def sync_trello_to_dust():
    print("Fetching Trello data...")
    lists = get_trello_lists()
    cards = get_trello_cards()
    print(f"Found {len(cards)} cards across {len(lists)} lists.")

    for i, card in enumerate(cards):
        list_name = lists.get(card["idList"], "Unknown List")
        text = format_card_text(card, list_name)
        try:
            upsert_to_dust(
                card_id=card["id"],
                title=card["name"],
                text=text,
                source_url=card.get("url", ""),
                timestamp=card.get("dateLastActivity", datetime.utcnow().isoformat() + "Z"),
            )
            print(f"[{i+1}/{len(cards)}] ✅ Synced: {card['name']}")
        except Exception as e:
            print(f"[{i+1}/{len(cards)}] ❌ Failed: {card['name']} — {e}")

    print("\nSync complete!")

if __name__ == "__main__":
    sync_trello_to_dust()
