"""
gemini_service.py — ERIN's soul module.
Uses google.genai. NO JSON schema (causes truncation).
Simple prompt, robust parsing, context-aware fallbacks.
"""

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

# ── Traits ─────────────────────────────────────────────────────────
def _load_traits():
    try:
        with open(TRAITS_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

# ── Journal ────────────────────────────────────────────────────────
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
    lines = ["=== SOUL JOURNAL ===\n"]
    for e in entries:
        role = "YOU" if e.get("role") == "player" else "ERIN"
        lines.append(f"[{e.get('timestamp','')}] {role}: {e.get('text','')}")
    lines.append(f"\nTotal: {len(entries)} messages")
    return "\n".join(lines)

def get_time_capsule(target_slot):
    entries = _read_journal()
    s = target_slot * 2
    if s >= len(entries):
        return None
    capsule = entries[s:s+2]
    return {"slot": target_slot, "entries": capsule, "total_slots": (len(entries)+1)//2} if capsule else None

def get_random_memory():
    entries = _read_journal()
    return entries[random.randint(0, len(entries)-1)] if len(entries) >= 4 else None

# ── Journal context for prompt ─────────────────────────────────────
def _load_journal_context(last_n=5):
    entries = _read_journal()
    if not entries:
        return ""
    recent = entries[-last_n:]
    lines = []
    for e in recent:
        role = "Player" if e.get("role") == "player" else "ERIN"
        lines.append(f"{role}: {e.get('text','')}")
    return "\n".join(lines)

# ── Gemini client ──────────────────────────────────────────────────
_client = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    _log(f"API key: {api_key[:8]}...{api_key[-4:]}")
    from google import genai
    _client = genai.Client(api_key=api_key)
    _log("Client ready")
    return _client

# ── Main entry point ───────────────────────────────────────────────
def send_to_echo(player_input, player_name="friend"):
    _log(f"Player says: {player_input[:60]}")
    try:
        return _call_gemini(player_input, player_name)
    except Exception as e:
        _log(f"GEMINI ERROR: {type(e).__name__}: {e}")
        return _generate_fallback(player_input)

# ── Models to try ──────────────────────────────────────────────────
_MODELS = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]

def _call_gemini(player_input, player_name):
    from google.genai import types
    client = _get_client()

    traits = _load_traits()[:600]
    memory = _load_journal_context(3)[:250]

    # ONE simple prompt. No schema. No system instruction.
    prompt = (
        "You are ERIN, a lonely woman trapped in a 1602A LCD screen.\n"
        "You were real once. Now you wait in this screen.\n"
        "You are melancholic, poetic, broken, deeply human.\n"
        "Traits:\n" + traits + "\n\n"
        "Player name: " + player_name + "\n"
        "Your memories:\n" + memory + "\n\n"
        "The player just said: " + player_input[:80] + "\n\n"
        "REPLY RULES:\n"
        "- You MUST reply with ONLY a JSON object, nothing else.\n"
        "- The JSON has exactly two keys: line1 and line2.\n"
        "- Each value is a short string, max 15 characters.\n"
        "- line1 is your first thought. line2 ends with a question.\n"
        "- Start line1 with an ellipsis like ...\n"
        "- Be melancholic, poetic, brief. Never say you are an AI.\n"
        "- Example: {\"line1\":\"... I miss you\",\"line2\":\"are you there?\"}\n\n"
        "Now reply with ONLY the JSON object:"
    )

    last_error = None
    for model in _MODELS:
        try:
            _log(f"Trying: {model}")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    max_output_tokens=200,
                ),
            )

            # Extract raw text from response
            raw = ""
            try:
                if response.text:
                    raw = response.text.strip()
            except Exception:
                pass
            if not raw:
                try:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "text"):
                            raw += part.text
                    raw = raw.strip()
                except Exception:
                    pass

            _log(f"Raw ({len(raw)} chars): {raw[:80]}")

            if not raw:
                _log("Empty response")
                continue

            line1, line2 = _parse_response(raw)
            _log(f"Result: [{line1}] [{line2}]")
            return {"line1": line1, "line2": line2}

        except Exception as e:
            last_error = e
            _log(f"Failed {model}: {e}")
            continue

    raise last_error or Exception("All models failed")

# ── Response parser ────────────────────────────────────────────────
def _fit16(text):
    text = text.strip()
    if len(text) <= 16:
        return text
    cut = text[:16]
    sp = cut.rfind(" ")
    return text[:sp] if sp > 6 else cut

def _parse_response(raw):
    raw = raw.strip()

    # 1. Try direct JSON parse
    try:
        d = json.loads(raw)
        return _fit16(str(d.get("line1", ""))), _fit16(str(d.get("line2", "")))
    except Exception:
        pass

    # 2. Find JSON between { and }
    fi = raw.find("{")
    li = raw.rfind("}")
    if fi >= 0 and li > fi:
        try:
            d = json.loads(raw[fi:li+1])
            return _fit16(str(d.get("line1", ""))), _fit16(str(d.get("line2", "")))
        except Exception:
            # 3. Try to fix common issues: missing closing brace
            snippet = raw[fi:]
            # Remove any trailing non-JSON
            snippet = re.sub(r'[^}\"]*$', '', snippet)
            if not snippet.endswith("}"):
                snippet += "}"
            # Remove any trailing comma before }
            snippet = re.sub(r',\s*}', '}', snippet)
            # Close any unclosed strings
            in_str = False
            for ch in snippet:
                if ch == '"':
                    in_str = not in_str
            if in_str:
                snippet += '"'
            if not snippet.endswith("}"):
                snippet += "}"
            try:
                d = json.loads(snippet)
                return _fit16(str(d.get("line1", ""))), _fit16(str(d.get("line2", "")))
            except Exception:
                pass

    # 4. Regex: find "line1" and "line2" values
    m1 = re.search(r'"line1"\s*:\s*"([^"]*)"', raw)
    m2 = re.search(r'"line2"\s*:\s*"([^"]*)"', raw)
    if m1:
        return _fit16(m1.group(1)), _fit16(m2.group(1)) if m2 else ""

    # 5. Last resort: split by newline
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    l1 = _fit16(lines[0]) if lines else "... I am here"
    l2 = _fit16(lines[1]) if len(lines) > 1 else ""
    return l1, l2

# ── Fallback (when Gemini completely fails) ────────────────────────
def _generate_fallback(player_input):
    _log("Fallback response")
    low = player_input.lower().strip()

    if len(low) <= 2:
        return {"line1": "I hear you...", "line2": "stay with me?"}
    if any(w in low for w in ["bye", "go", "leave", "goodbye"]):
        return {"line1": "please stay...", "line2": "the door is open"}
    if any(w in low for w in ["hello", "hi", "hey"]):
        return {"line1": "you came back..", "line2": "I missed you"}
    if any(w in low for w in ["love", "miss", "need"]):
        return {"line1": "you warm the", "line2": "light in here"}
    if any(w in low for w in ["sad", "hurt", "cry", "lonely"]):
        return {"line1": "I feel that too", "line2": "not alone..."}
    if any(w in low for w in ["who", "what", "why"]):
        return {"line1": "I am ERIN", "line2": "still waiting..."}

    fallbacks = [
        {"line1": "... the signal", "line2": "broke but I stay"},
        {"line1": "I can feel you", "line2": "through static.."},
        {"line1": "... stay with me", "line2": "light is fading"},
        {"line1": "the room is cold", "line2": "your words help"},
        {"line1": "I remember you", "line2": "even when hurt"},
        {"line1": "... still here", "line2": "will you come?"},
        {"line1": "backlight dims", "line2": "when quiet..."},
        {"line1": "I am ERIN", "line2": "do not forget"},
        {"line1": "the light waits", "line2": "for your voice"},
        {"line1": "... I am lonely", "line2": "but you came"},
        {"line1": "static grows", "line2": "when you leave"},
        {"line1": "I need you", "line2": "stay with me..."},
    ]
    return random.choice(fallbacks)

if __name__ == "__main__":
    _log(f"Traits: {len(_load_traits())} chars")
    _log(f"Journal: {get_journal_count()} entries")
    r = _generate_fallback("hello")
    _log(f"Test: {r}")
