import os
import json
import time
from datetime import datetime

JOURNAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "echoes_journal.json")

def _read_journal():
    if not os.path.exists(JOURNAL_PATH):
        return []
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _write_journal(entries):
    tmp = JOURNAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp, JOURNAL_PATH)

def save_to_journal(role, text):
    entries = _read_journal()
    entries.append({"role": role, "text": text, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _write_journal(entries)

def get_journal_count():
    return len(_read_journal())

def get_journal_entries(last_n=None):
    entries = _read_journal()
    return entries[-last_n:] if last_n else entries

def search_journal(keyword):
    entries = _read_journal()
    kw = keyword.lower()
    return [e for e in entries if kw in e.get("text", "").lower()]

def export_journal_text():
    entries = _read_journal()
    lines = ["=== THE LAST APARTMENT — SOUL JOURNAL ===\n"]
    for e in entries:
        role = "YOU" if e.get("role") == "player" else "ERIN"
        lines.append(f"[{e.get('timestamp','')}] {role}: {e.get('text','')}")
    lines.append(f"\nTotal: {len(entries)} messages")
    return "\n".join(lines)