import os
import requests
import json
from datetime import datetime, timezone

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

# --- Helpers ---
def _now():
    return datetime.now(timezone.utc)

def _parse_iso(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def _days_ago(ts):
    if not ts:
        return None
    return (_now() - _parse_iso(ts)).days

def get_card_actions(card_id):
    url = f"https://api.trello.com/1/cards/{card_id}/actions"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "filter": "commentCard,addMemberToCard",
        "limit": 1000,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()  # newest first

def compute_temporal_fields(card, actions):
    now = _now()
    comments = [a for a in actions if a["type"] == "commentCard"]
    assignments = [a for a in actions if a["type"] == "addMemberToCard"]

    days_until_due = (_parse_iso(card["due"]) - now).days if card.get("due") else None

    has_had_no_activity_since_assigned = False
    if assignments:
        last_assign = _parse_iso(assignments[0]["date"])
        non_assign_after = [
            a for a in actions
            if a["type"] != "addMemberToCard" and _parse_iso(a["date"]) > last_assign
        ]
        has_had_no_activity_since_assigned = not non_assign_after

    return {
        "days_since_last_activity": _days_ago(card.get("dateLastActivity")),
        "days_since_last_comment": _days_ago(comments[0]["date"]) if comments else None,
        "days_until_due": days_until_due,
        "has_had_no_activity_since_assigned": has_had_no_activity_since_assigned,
    }

# --- Step 2: Fetch all cards from the Trello board ---
def get_trello_cards():
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/cards"
    params = {
        "key": TRELLO_API_KEY,
        "token": TRELLO_TOKEN,
        "fields": "id,name,desc,url,idList,labels,due,dueComplete,dateLastActivity,address,locationName,coordinates",
        "checklists": "all",
        "members": "true",
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

# --- Step 3: Format a card as text for Dust ---
def format_card_text(card, list_name, temporal, actions):
    def _fmt(v, none_label="n/a"):
        return none_label if v is None else v

    lines = [
        f"# {card['name']}",
        f"**List:** {list_name}",
        f"**Completed:** {bool(card.get('dueComplete'))}",
        f"**URL:** {card.get('url', 'N/A')}",
        f"**Due Date:** {card.get('due') or 'None'}",
        f"**Last Activity:** {card.get('dateLastActivity', 'N/A')}",
        "",
        "## Temporal signals",
        f"- days_since_last_activity: {_fmt(temporal['days_since_last_activity'])}",
        f"- days_since_last_comment: {_fmt(temporal['days_since_last_comment'], 'never')}",
        f"- days_until_due: {_fmt(temporal['days_until_due'], 'no due date')}",
        f"- has_had_no_activity_since_assigned: {temporal['has_had_no_activity_since_assigned']}",
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

    comments = [a for a in actions if a["type"] == "commentCard"]
    if comments:
        lines.append("\n## Comments")
        for c in reversed(comments):  # oldest first for readability
            author = (c.get("memberCreator") or {}).get("fullName", "Unknown")
            date = c.get("date", "")[:10]
            text = (c.get("data") or {}).get("text", "")
            lines.append(f"\n**{date} — {author}**")
            for line in text.splitlines() or [""]:
                lines.append(f"> {line}")

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
        try:
            actions = get_card_actions(card["id"])
            temporal = compute_temporal_fields(card, actions)
            text = format_card_text(card, list_name, temporal, actions)
            upsert_to_dust(
                card_id=card["id"],
                title=card["name"],
                text=text,
                source_url=card.get("url", ""),
                timestamp=card.get("dateLastActivity", _now().isoformat().replace("+00:00", "Z")),
            )
            print(f"[{i+1}/{len(cards)}] ✅ Synced: {card['name']}")
        except Exception as e:
            print(f"[{i+1}/{len(cards)}] ❌ Failed: {card['name']} — {e}")

    print("\nSync complete!")

if __name__ == "__main__":
    sync_trello_to_dust()
