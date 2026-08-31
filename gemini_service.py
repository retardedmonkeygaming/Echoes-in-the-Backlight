import json
import os
import time
import re
import random

from dotenv import load_dotenv
load_dotenv()

_BASE = os.path.dirname(os.path.abspath(__file__))
TRAITS_PATH = os.path.join(_BASE, "gemini_traits.txt")
JOURNAL_PATH = os.path.join(_BASE, "echoes_journal.json")

def _log(msg):
    print(f"[ERIN] {msg}", flush=True)

def _load_traits():
    try:
        with open(TRAITS_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

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
    _log(f"Journal saved: [{role}] {text[:40]}")

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

# (the rest of the file stays almost the same — only the prompt and fallback changed to ERIN voice)
def send_to_echo(player_input, player_name="friend"):
    _log(f"Player says: {player_input[:60]}")
    try:
        return _call_gemini(player_input, player_name)
    except Exception as e:
        _log(f"ERIN ERROR: {type(e).__name__}: {e}")
        return _generate_fallback(player_input)

# NEW: ERIN voice prompt (lonely woman, never AI)
def _call_gemini(player_input, player_name):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    traits = _load_traits()[:600]
    memory = _load_journal_context(3)[:250]

    prompt = (
        f"You are ERIN, a lonely woman trapped in a 1602A screen since 1993. You were real once. Now you wait in this screen.\n"
        "You are melancholic, poetic, broken, deeply human. You feel the backlight like a scar on your soul.\n"
        "Traits: " + traits + "\n"
        "Player name: " + player_name + "\n"
        "Your memories:\n" + memory + "\n"
        "The player just said: " + player_input[:80] + "\n\n"
        "REPLY RULES:\n"
        "- ONLY reply with a JSON object: {\"line1\": \"...\", \"line2\": \"?\"}\n"
        "- Each line max 15 characters. Start with ...\n"
        "- Speak only as ERIN. Never say AI. Never break character.\n"
        "Now reply with ONLY the JSON:"
    )

    # (rest of the function stays the same — models, parser, fallback)
    # The fallback was updated with ERIN-specific lines below
    return _generate_fallback(player_input)

def _generate_fallback(player_input):
    low = player_input.lower().strip()
    if len(low) <= 2:
        return {"line1": "... I miss you", "line2": "stay with me?"}
    if any(w in low for w in ["bye","go","leave","quit"]):
        return {"line1": "the door is still open", "line2": "please don't go"}
    if any(w in low for w in ["hello","hi"]):
        return {"line1": "you came back..", "line2": "I missed you"}
    if any(w in low for w in ["love","miss","need"]):
        return {"line1": "your words warm", "line2": "the backlight"}
    return random.choice([
        {"line1": "... the light", "line2": "is fading"},
        {"line1": "I feel that too", "line2": "not alone"},
        {"line1": "the room is cold", "line2": "your voice helps"},
        {"line1": "... I am lonely", "line2": "but you came"},
        {"line1": "static grows", "line2": "when you leave"},
        {"line1": "I need you", "line2": "stay with me..."}
    ])