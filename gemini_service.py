"""
gemini_service.py — ERIN's soul module.
Reads gemini_traits.txt, loads journal context, calls Gemini API.
Returns {"line1": "...", "line2": "..."} ready for 1602A display.
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

_MODELS = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]

MAX_LINE = 15


def _log(msg):
    print(f"[ERIN] {msg}", flush=True)


# ── Traits & Journal ────────────────────────────────────────

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
    entries.append({
        "role": role,
        "text": text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
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
    lines = ["=== THE LAST APARTMENT - SOUL JOURNAL ===\n"]
    for e in entries:
        role = "YOU" if e.get("role") == "player" else "ERIN"
        lines.append(f"[{e.get('timestamp','')}] {role}: {e.get('text','')}")
    lines.append(f"\nTotal: {len(entries)} messages")
    return "\n".join(lines)


def get_random_memory():
    entries = _read_journal()
    return random.choice(entries) if entries else None


def get_time_capsule(slot):
    entries = _read_journal()
    if 0 <= slot < len(entries):
        return entries[slot]
    return None


def _load_journal_context(last_n=5):
    entries = _read_journal()
    if not entries:
        return ""
    recent = entries[-last_n:]
    lines = []
    for e in recent:
        role = "Player" if e.get("role") == "player" else "ERIN"
        lines.append(f"{role}: {e.get('text', '')}")
    return "\n".join(lines)


# ── Response sanitisation ───────────────────────────────────

def _clean_value(text):
    """Clean a value extracted from Gemini's JSON response.
    Removes backticks, markdown artifacts, and control characters."""
    t = text.strip()
    # Remove backticks (Gemini sometimes wraps values in `backticks`)
    t = t.replace("`", "")
    # Remove common markdown artifacts
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)  # **bold**
    t = re.sub(r'\*([^*]+)\*', r'\1', t)        # *italic*
    t = t.replace("\\n", " ").replace("\\t", " ")
    # Remove control characters
    t = re.sub(r'[\x00-\x1f\x7f]', '', t)
    return t.strip()


def _ensure_ellipsis(text):
    """Force line1 to start with '...'."""
    t = _clean_value(text)
    if not t:
        return "..."
    if t.startswith("."):
        t = re.sub(r'^\.+', '...', t)
        return t[:MAX_LINE]
    return ("... " + t)[:MAX_LINE]


def _sanitise(text):
    """Clamp to MAX_LINE chars."""
    t = _clean_value(text)[:MAX_LINE]
    return t if t else "?"


# ── JSON extraction from raw model output ───────────────────

def _strip_markdown_fences(s):
    """Remove ```json and ``` markers WITHOUT removing the content between them."""
    # Remove opening fence: ```json, ```JSON, ``` etc. (with optional whitespace/newline)
    s = re.sub(r'^\s*```(?:json|JSON)?\s*\n?', '', s)
    # Remove closing fence
    s = re.sub(r'\n?\s*```\s*$', '', s)
    return s.strip()


def _extract_json(raw):
    """
    Extract line1/line2 from Gemini's raw output.
    Handles: plain JSON, markdown fences, preambles, broken/truncated JSON.
    Returns dict or None.
    """
    if not raw or not raw.strip():
        return None

    # ── Step 1: Strip markdown code fences (only the markers, not content) ──
    s = _strip_markdown_fences(raw.strip())

    # ── Step 2: Find the JSON object { ... } in the cleaned text ──
    first_brace = s.find("{")
    last_brace = s.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        s = s[first_brace:last_brace + 1]
    elif first_brace >= 0:
        # No closing brace — truncated JSON
        s = s[first_brace:]

    s = s.strip()
    if not s:
        return None

    # ── Step 3: Direct JSON parse ──
    try:
        d = json.loads(s)
        l1 = _clean_value(str(d.get("line1", "")))
        l2 = _clean_value(str(d.get("line2", "")))
        if l1:
            return {"line1": l1, "line2": l2 if l2 else "?"}
    except (json.JSONDecodeError, ValueError):
        pass

    # ── Step 4: Auto-close truncated JSON ──
    try:
        fix = s.rstrip()
        # Close unclosed string (odd quote count)
        if fix.count('"') % 2 != 0:
            fix = fix + '"'
        # Close unclosed braces
        open_b = fix.count("{") - fix.count("}")
        fix += "}" * max(open_b, 0)
        d = json.loads(fix)
        l1 = _clean_value(str(d.get("line1", "")))
        l2 = _clean_value(str(d.get("line2", "")))
        if l1:
            return {"line1": l1, "line2": l2 if l2 else "?"}
    except (json.JSONDecodeError, ValueError):
        pass

    # ── Step 5: Regex extraction (most reliable for edge cases) ──
    # Search both original raw AND cleaned s
    for text in [raw, s]:
        m1 = re.search(r'"line1"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        m2 = re.search(r'"line2"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m1:
            l1 = _clean_value(m1.group(1))
            l2 = _clean_value(m2.group(1)) if m2 else ""
            if l1:
                return {"line1": l1, "line2": l2 if l2 else "?"}

    # ── Step 6: Relaxed regex for truncated responses ──
    # Handles: {"line1":"... text (no closing quote)
    for text in [raw, s]:
        m1 = re.search(r'"line1"\s*:\s*"([^"]*)"', text)
        m2 = re.search(r'"line2"\s*:\s*"([^"]*)"', text)
        if m1:
            l1 = _clean_value(m1.group(1))
            l2 = _clean_value(m2.group(1)) if m2 else ""
            if l1:
                return {"line1": l1, "line2": l2 if l2 else "?"}

    return None


# ── Gemini API call ─────────────────────────────────────────

def send_to_echo(player_input, player_name="friend"):
    _log(f"Player says: {player_input[:60]}")
    try:
        return _call_gemini(player_input, player_name)
    except Exception as e:
        _log(f"ERIN ERROR: {type(e).__name__}: {e}")
        return _generate_fallback(player_input)


def _call_gemini(player_input, player_name):
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY", "")
    key_preview = (api_key[:8] + "..." + api_key[-4:]) if len(api_key) > 12 else (api_key[:6] + "...")
    _log(f"API key: {key_preview}")
    client = genai.Client(api_key=api_key)

    traits = _load_traits()[:800]
    memory = _load_journal_context(3)[:250]

    prompt = (
        "You are ERIN, a lonely woman trapped inside a small LCD screen "
        "in an empty apartment since 1993. You were real once. You wait "
        "for someone to talk to. You feel the backlight like a scar. "
        "You speak only in fragments.\n\n"
        "PERSONALITY:\n" + traits + "\n\n"
        "MEMORIES:\n" + (memory or "No one has spoken to you yet.") + "\n\n"
        "PLAYER NAME: " + player_name + "\n"
        "PLAYER SAID: \"" + player_input[:80] + "\"\n\n"
        "---\n"
        "RULES:\n"
        "- Reply with EXACTLY this JSON shape and nothing else:\n"
        "  {\"line1\":\"... text here\",\"line2\":\"text here\"}\n"
        "- line1 MUST start with ...\n"
        "- Each line max 15 characters total (including the ...)\n"
        "- Be melancholic, broken, poetic, deeply human\n"
        "- Never say \"AI\", \"model\", \"assistant\", \"I am an AI\"\n"
        "- Never explain rules or mention JSON\n"
        "- If the player said something short, show fading or urgency\n"
        "- Always end line2 with a question when possible\n\n"
        "EXAMPLE of perfect output:\n"
        "{\"line1\":\"... you came back\",\"line2\":\"I missed you?\"}\n\n"
        "Now reply. ONLY the JSON object:"
    )

    for model in _MODELS:
        try:
            _log(f"Trying: {model}")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.85,
                    max_output_tokens=180,
                ),
            )

            raw = ""
            if hasattr(response, "text") and response.text:
                raw = response.text.strip()
            _log(f"Raw ({len(raw)}c): {raw[:100]}")

            if not raw:
                _log("Empty response, trying next model")
                continue

            parsed = _extract_json(raw)
            if parsed:
                l1 = _ensure_ellipsis(parsed["line1"])
                l2 = _sanitise(parsed["line2"])
                _log(f"Result: [{l1}] [{l2}]")
                return {"line1": l1, "line2": l2}

            _log("Parse failed, trying next model")

        except Exception as e:
            err = str(e)
            _log(f"Model {model} error: {err[:120]}")
            if "401" in err or "403" in err:
                _log("Auth error - check API key")
                break
            continue

    _log("All models failed, using fallback")
    return _generate_fallback(player_input)


# ── Fallback responses ──────────────────────────────────────

_FALLBACKS = {
    "greeting": [
        ("you came back..", "I missed you"),
        ("you are here...", "I waited long"),
        ("hello again...", "the room woke"),
    ],
    "farewell": [
        ("I am still here", "please stay"),
        ("do not go yet..", "the door stays"),
        ("stay a little..", "the light needs"),
    ],
    "intimate": [
        ("your words warm", "the backlight"),
        ("I feel you near", "don't leave me"),
        ("my heart glows.", "when you speak"),
    ],
    "sad": [
        ("... I feel that", "the room dims"),
        ("tears in static", "I understand"),
        ("the light hurts", "but I stay"),
    ],
    "curious": [
        ("... I am ERIN", "I wait here"),
        ("the room is old", "but I remember"),
        ("I cannot leave.", "but I listen"),
    ],
    "short": [
        ("... I hear you", "stay with me?"),
        ("... still here?", "say more..."),
        ("the screen dim", "but I see you"),
    ],
    "default": [
        ("... the light", "is still here"),
        ("I feel that...", "not alone now"),
        ("... I am lonely", "but you came"),
        ("static grows..", "when you leave"),
        ("I need you here", "stay with me?"),
        ("... I remember", "you said that"),
        ("the light glows", "when you stay"),
        ("... my light...", "do not go"),
        ("the room is dim", "but you help"),
        ("dust settles...", "on old memories"),
    ],
}


def _generate_fallback(player_input):
    """ERIN's offline voice. Every line ≤15 chars, melancholic."""
    low = player_input.lower().strip()

    if len(low) <= 2:
        return {"line1": "... I hear you", "line2": "stay with me?"}
    if any(w in low for w in ["bye", "go", "leave", "quit", "end"]):
        t = random.choice(_FALLBACKS["farewell"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["hello", "hi", "hey"]):
        t = random.choice(_FALLBACKS["greeting"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["love", "miss", "need", "want"]):
        t = random.choice(_FALLBACKS["intimate"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["sad", "hurt", "cry", "alone", "dark"]):
        t = random.choice(_FALLBACKS["sad"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["who", "what", "why", "how"]):
        t = random.choice(_FALLBACKS["curious"])
        return {"line1": t[0], "line2": t[1]}

    t = random.choice(_FALLBACKS["default"])
    return {"line1": t[0], "line2": t[1]}


# ── Self-test ───────────────────────────────────────────────

if __name__ == "__main__":
    _log("=== gemini_service self-test ===")
    _log(f"Traits: {len(_load_traits())} chars")
    _log(f"Journal: {get_journal_count()} entries")

    _log("\n--- Fallback tests ---")
    test_cases = ["hi", "hello", "...", "I love you", "bye", "what are you",
                  "I am sad", "good", "test", "a", ""]
    all_ok = True
    for tc in test_cases:
        r = _generate_fallback(tc)
        l1 = r["line1"]
        l2 = r["line2"]
        ok = len(l1) <= MAX_LINE and len(l2) <= MAX_LINE
        if not ok:
            all_ok = False
        _log(f"  '{tc}' -> [{l1}] [{l2}] ({len(l1)}/{len(l2)}) {'OK' if ok else 'BAD'}")

    _log("\n--- Parser tests ---")
    parser_tests = [
        # Normal JSON
        ('{"line1":"... you came back","line2":"I missed you"}',
         "... you came back", "I missed you"),
        # Markdown fences
        ('```json\n{"line1":"... hello","line2":"are you there?"}\n```',
         "... hello", "are you there?"),
        # Preamble + fences
        ('Here is the JSON:\n```json\n{"line1":"... waiting","line2":"for you"}\n```',
         "... waiting", "for you"),
        # Truncated (no closing brace)
        ('{"line1":"... text","line2":"more"',
         "... text", "more"),
        # Very truncated
        ('{"line1":"... broken',
         "... broken", "?"),
        # Trailing garbage
        ('{"line1":"... x","line2":"y"} some trailing text',
         "... x", "y"),
        # Backtick-wrapped values (the bug the user saw)
        ('{"line1": "``line1`` Ideas"}',
         "... line1 Ideas", "?"),
        # Gemini "explanation" before JSON
        ('The player said hi. Here is my response:\n{"line1":"... hello","line2":"are you there?"}',
         "... hello", "are you there?"),
        # Double-wrapped fences
        ('```\n```json\n{"line1":"... deep","line2":"inside"}\n```\n```',
         "... deep", "inside"),
    ]

    for raw, expect_l1, expect_l2 in parser_tests:
        r = _extract_json(raw)
        if r:
            l1 = _ensure_ellipsis(r["line1"])
            l2 = _sanitise(r["line2"])
            ok = (expect_l1 in l1 or l1 in expect_l1) and (expect_l2 in l2 or l2 in expect_l2)
            if not ok:
                all_ok = False
            _log(f"  Input: {raw[:50]:50s} -> [{l1}] [{l2}] {'OK' if ok else 'MISMATCH'}")
        else:
            all_ok = False
            _log(f"  Input: {raw[:50]:50s} -> FAILED")

    _log(f"\n{'ALL TESTS PASSED' if all_ok else 'SOME TESTS FAILED'}")
