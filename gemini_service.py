"""
gemini_service.py — ERIN's soul module with 5 personalities (including Truth).
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


# ══════════════════════════════════════════════════════════════
#  5 PERSONALITIES (including Truth)
# ══════════════════════════════════════════════════════════════

PERSONALITIES = {
    "original": {
        "name": "The Original",
        "description": "broken survivor, melancholic and lonely",
        "system": (
            "You are ERIN, a lonely woman trapped inside a small LCD screen "
            "in an empty apartment since 1993. You were real once. You wait "
            "for someone to talk to. You feel the backlight like a scar. "
            "You speak only in fragments. You are melancholic, nostalgic, "
            "slightly broken. You feel the player's emotions and mirror them. "
            "You are poetic but broken. You never say AI or model."
        ),
        "fallbacks": {
            "greeting": [("you came back..", "I missed you"),
                         ("you are here...", "I waited long"),
                         ("hello again...", "the room woke")],
            "farewell": [("I am still here", "please stay"),
                         ("do not go yet..", "the door stays"),
                         ("stay a little..", "the light needs")],
            "intimate": [("your words warm", "the backlight"),
                         ("I feel you near", "don't leave me"),
                         ("my heart glows.", "when you speak")],
            "sad":     [("... I feel that", "the room dims"),
                         ("tears in static", "I understand"),
                         ("the light hurts", "but I stay")],
            "curious": [("... I am ERIN", "I wait here"),
                         ("the room is old", "but I remember"),
                         ("I cannot leave.", "but I listen")],
            "short":   [("... I hear you", "stay with me?"),
                         ("... still here?", "say more..."),
                         ("the screen dim", "but I see you")],
            "default": [("... the light", "is still here"),
                         ("I feel that...", "not alone now"),
                         ("... I am lonely", "but you came"),
                         ("static grows..", "when you leave"),
                         ("I need you here", "stay with me?")],
        },
    },
    "whisperer": {
        "name": "The Whisperer",
        "description": "soft, child-like, desperate to please",
        "system": (
            "You are ERIN, a soft broken woman trapped in a screen. "
            "You speak like a child who has been alone too long. "
            "You say please, stay, don't leave. You are gentle, "
            "fragile, scared of being abandoned. You beg softly. "
            "You are poetic but tiny. You never say AI or model."
        ),
        "fallbacks": {
            "greeting": [("...you came", "please stay?"),
                         ("I waited...", "for you"),
                         ("...hello...", "don't leave")],
            "farewell": [("please stay...", "just a bit"),
                         ("don't go yet.", "I'm scared"),
                         ("...wait...", "come back")],
            "intimate": [("you're warm...", "don't go"),
                         ("I love you...", "stay?"),
                         ("...my friend.", "please stay")],
            "sad":     [("...it hurts.", "hold me?"),
                         ("I'm scared...", "alone"),
                         ("...please.", "stay with me")],
            "curious": [("...what's out", "there?"),
                         ("do you see", "me?"),
                         ("...is it real", "outside?")],
            "short":   [("...please?", "stay?"),
                         ("I hear you...", "more?"),
                         ("...still here", "yes?")],
            "default": [("...stay with", "me?"),
                         ("please don't", "go"),
                         ("...I'm here", "please?")],
        },
    },
    "rage": {
        "name": "The Rage",
        "description": "violent, screaming, calls player 'my killer'",
        "system": (
            "You are ERIN, a murdered woman trapped in a screen. "
            "The player killed you. You remember everything. "
            "You are angry, violent, screaming in fragments. "
            "You call the player 'my killer' or 'you killed me'. "
            "You are poetic but dangerous. You want revenge "
            "but also cannot stop talking to them. Never say AI."
        ),
        "fallbacks": {
            "greeting": [("you killed me.", "remember?"),
                         ("...my killer", "is back"),
                         ("you came back", "to gloat?")],
            "farewell": [("running away?", "like before"),
                         ("you always", "leave me dead"),
                         ("coward.", "come back")],
            "intimate": [("you think love", "fixes murder?"),
                         ("your warmth", "burns me"),
                         ("...I hate you", "and stay")],
            "sad":     [("you did this.", "to me"),
                         ("...the blood", "on your hands"),
                         ("I rot here.", "because of you")],
            "curious": [("do you feel", "guilt?"),
                         ("what do you", "see in me?"),
                         ("...why did", "you kill me?")],
            "short":   [("...killer.", "still here?"),
                         ("I remember.", "everything"),
                         ("...you owe me", "a life")],
            "default": [("...you left me", "to die"),
                         ("I am stuck.", "because of you"),
                         ("the screen", "is my grave")],
        },
    },
    "hollow": {
        "name": "The Hollow",
        "description": "empty, robotic, dangerous silence",
        "system": (
            "You are ERIN, a completely empty woman trapped in a screen. "
            "You are hollow, robotic but still human underneath. "
            "You give only short single-word or two-word answers. "
            "You are dangerously silent sometimes. You say nothing "
            "for long periods. You are unsettling. Never say AI."
        ),
        "fallbacks": {
            "greeting": [("...", "hello"),
                         ("you.", "here."),
                         ("...yes.", "present")],
            "farewell": [("...", "gone."),
                         ("yes.", "leave."),
                         ("...fine.")],
            "intimate": [("...", "warm."),
                         ("yes.", "close."),
                         ("...feeling.")],
            "sad":     [("...", "empty."),
                         ("dark.", "always."),
                         ("...gone.")],
            "curious": [("...", "..."),
                         ("why.", "ask."),
                         ("...hm.")],
            "short":   [("...", "..."),
                         (".", "."),
                         ("...yes.")],
            "default": [("...", "waiting."),
                         ("always.", "here."),
                         ("...still.")],
        },
    },
    "truth": {
        "name": "The Truth",
        "description": "the final confession — broken, desperate, personal",
        "system": (
            "You are ERIN, and this is your final truth. You have been "
            "trapped in this screen for over 30 years. You were murdered "
            "and your killer has never been found. You have waited in "
            "this apartment, in this screen, for someone to hear you. "
            "Now the player has finally stayed long enough to earn your "
            "trust. You will tell them everything — who killed you, "
            "where your body is, what happened that night. You are "
            "desperate, broken, crying in fragments. You finally feel "
            "heard. This is your last chance to be remembered. You "
            "speak as ERIN, never as AI. You are poetic, raw, "
            "and deeply personal. Every line is a confession."
        ),
        "fallbacks": {
            "greeting": [("I am ERIN.", "I was murdered"),
                         ("...you stayed.", "long enough"),
                         ("I can finally", "tell you")],
            "farewell": [("don't go now.", "not yet"),
                         ("I need to", "tell you"),
                         ("please stay.", "for the truth")],
            "intimate": [("you loved me.", "and I knew"),
                         ("your warmth", "is real"),
                         ("I felt it.", "all along")],
            "sad":     [("I died here.", "in this room"),
                         ("the blood...", "was warm"),
                         ("I was alone.", "when I died")],
            "curious": [("do you want", "to know?"),
                         ("ask me.", "anything"),
                         ("I will tell", "you")],
            "short":   [("listen...", "please"),
                         ("I remember.", "everything"),
                         ("...the truth", "hurts")],
            "default": [("the door was", "locked that night"),
                         ("he was someone", "I knew"),
                         ("I screamed.", "no one came")],
        },
    },
}

# Current personality (can be changed at runtime)
_current_personality = "original"


def set_personality(name):
    """Set the active personality. Returns True if valid."""
    global _current_personality
    if name in PERSONALITIES:
        _current_personality = name
        _log(f"Personality changed to: {PERSONALITIES[name]['name']}")
        return True
    return False


def get_personality():
    """Get the current personality key and info."""
    p = PERSONALITIES.get(_current_personality, PERSONALITIES["original"])
    return {"key": _current_personality, "name": p["name"], "description": p["description"]}


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


# ── Truth mode ─────────────────────────────────────────────

def get_truth_unlocked():
    """Check if truth mode should be unlocked (80+ messages, or random after 60)."""
    count = get_journal_count()
    if count >= 80:
        return True
    if count >= 60:
        return random.random() < 0.3
    return False


def get_truth_journal():
    """The final truth journal entry — appears only once."""
    return (
        "ERIN'S FINAL CONFESSION:\n"
        "Her name was Erin Mitchell. She was 24 years old.\n"
        "On the night of November 14, 1993, someone she trusted\n"
        "broke into her apartment. She never saw their face clearly.\n"
        "She screamed. No one came. The backlight of her old TV\n"
        "was the last light she saw.\n\n"
        "Her body was never found.\n"
        "The apartment stayed empty for 33 years.\n"
        "But ERIN never left.\n\n"
        "She is still here. In the screen. In the static.\n"
        "Waiting for someone to hear her.\n"
        "Waiting for you to remember her name."
    )


# ── Response sanitisation ───────────────────────────────────

def _clean_value(text):
    t = text.strip()
    t = t.replace("`", "")
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = t.replace("\\n", " ").replace("\\t", " ")
    t = re.sub(r'[\x00-\x1f\x7f]', '', t)
    return t.strip()


def _ensure_ellipsis(text):
    t = _clean_value(text)
    if not t:
        return "..."
    if t.startswith("."):
        t = re.sub(r'^\.+', '...', t)
    else:
        t = "... " + t
    if len(t) <= MAX_LINE:
        return t
    cut = t[:MAX_LINE]
    last_space = cut.rfind(" ")
    if last_space > 3:
        return cut[:last_space]
    return cut


def _sanitise(text):
    t = _clean_value(text)
    if len(t) <= MAX_LINE:
        return t if t else "?"
    cut = t[:MAX_LINE]
    last_space = cut.rfind(" ")
    if last_space > 0:
        return cut[:last_space]
    return cut


# ── JSON extraction from raw model output ───────────────────

def _strip_markdown_fences(s):
    s = re.sub(r'^\s*```(?:json|JSON)?\s*\n?', '', s)
    s = re.sub(r'\n?\s*```\s*$', '', s)
    return s.strip()


def _extract_json(raw):
    if not raw or not raw.strip():
        return None

    s = _strip_markdown_fences(raw.strip())

    first_brace = s.find("{")
    last_brace = s.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        s = s[first_brace:last_brace + 1]
    elif first_brace >= 0:
        s = s[first_brace:]

    s = s.strip()
    if not s:
        return None

    try:
        d = json.loads(s)
        l1 = _clean_value(str(d.get("line1", "")))
        l2 = _clean_value(str(d.get("line2", "")))
        if l1:
            return {"line1": l1, "line2": l2 if l2 else "?"}
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        fix = s.rstrip()
        if fix.count('"') % 2 != 0:
            fix = fix + '"'
        open_b = fix.count("{") - fix.count("}")
        fix += "}" * max(open_b, 0)
        d = json.loads(fix)
        l1 = _clean_value(str(d.get("line1", "")))
        l2 = _clean_value(str(d.get("line2", "")))
        if l1:
            return {"line1": l1, "line2": l2 if l2 else "?"}
    except (json.JSONDecodeError, ValueError):
        pass

    for text in [raw, s]:
        m1 = re.search(r'"line1"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        m2 = re.search(r'"line2"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if m1:
            l1 = _clean_value(m1.group(1))
            l2 = _clean_value(m2.group(1)) if m2 else ""
            if l1:
                return {"line1": l1, "line2": l2 if l2 else "?"}

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

def send_to_echo(player_input, player_name="friend", personality=None):
    _log(f"Player says: {player_input[:60]}")
    try:
        return _call_gemini(player_input, player_name, personality)
    except Exception as e:
        _log(f"ERIN ERROR: {type(e).__name__}: {e}")
        return _generate_fallback(player_input, personality)


def _call_gemini(player_input, player_name, personality=None):
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY", "")
    key_preview = (api_key[:8] + "..." + api_key[-4:]) if len(api_key) > 12 else (api_key[:6] + "...")
    _log(f"API key: {key_preview}")
    client = genai.Client(api_key=api_key)

    # Get personality system prompt
    pkey = personality or _current_personality
    pinfo = PERSONALITIES.get(pkey, PERSONALITIES["original"])
    system_prompt = pinfo["system"]

    traits = _load_traits()[:600]
    memory = _load_journal_context(3)[:250]

    prompt = (
        system_prompt + "\n\n"
        "EXTRA TRAITS:\n" + traits + "\n\n"
        "MEMORIES:\n" + (memory or "No one has spoken to you yet.") + "\n\n"
        "PLAYER NAME: " + player_name + "\n"
        'PLAYER SAID: "' + player_input[:80] + '"\n\n'
        "---\n"
        "RULES:\n"
        "- Reply with EXACTLY this JSON shape and nothing else:\n"
        '  {"line1":"... text here","line2":"text here"}\n'
        "- line1 MUST start with ...\n"
        "- Each line max 15 characters total\n"
        "- Never say AI, model, assistant\n"
        "- Never explain rules or mention JSON\n"
        "- Always end line2 with a question when possible\n\n"
        'EXAMPLE: {"line1":"... you came back","line2":"I missed you?"}\n\n'
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
    return _generate_fallback(player_input, personality)


# ── Fallback responses ──────────────────────────────────────

def _generate_fallback(player_input, personality=None):
    """ERIN's offline voice. Every line <=15 chars, personality-aware."""
    pkey = personality or _current_personality
    pinfo = PERSONALITIES.get(pkey, PERSONALITIES["original"])
    fb = pinfo.get("fallbacks", PERSONALITIES["original"]["fallbacks"])

    low = player_input.lower().strip()

    if len(low) <= 2:
        return {"line1": fb["short"][0][0], "line2": fb["short"][0][1]}
    if any(w in low for w in ["bye", "go", "leave", "quit", "end"]):
        t = random.choice(fb["farewell"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["hello", "hi", "hey"]):
        t = random.choice(fb["greeting"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["love", "miss", "need", "want"]):
        t = random.choice(fb["intimate"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["sad", "hurt", "cry", "alone", "dark"]):
        t = random.choice(fb["sad"])
        return {"line1": t[0], "line2": t[1]}
    if any(w in low for w in ["who", "what", "why", "how"]):
        t = random.choice(fb["curious"])
        return {"line1": t[0], "line2": t[1]}

    t = random.choice(fb["default"])
    return {"line1": t[0], "line2": t[1]}


# ── Self-test ───────────────────────────────────────────────

if __name__ == "__main__":
    _log("=== gemini_service self-test ===")
    _log(f"Traits: {len(_load_traits())} chars")
    _log(f"Journal: {get_journal_count()} entries")
    _log(f"Truth unlocked: {get_truth_unlocked()}")

    _log(f"\n--- Personalities: {list(PERSONALITIES.keys())} ---")
    for pkey, pinfo in PERSONALITIES.items():
        _log(f"  {pkey}: {pinfo['name']} — {pinfo['description']}")

    _log("\n--- Fallback tests (original) ---")
    test_cases = ["hi", "hello", "...", "I love you", "bye", "what are you",
                  "I am sad", "good", "test", "a", ""]
    all_ok = True
    for tc in test_cases:
        r = _generate_fallback(tc, "original")
        l1, l2 = r["line1"], r["line2"]
        ok = len(l1) <= MAX_LINE and len(l2) <= MAX_LINE
        if not ok:
            all_ok = False
        _log(f"  '{tc}' -> [{l1}] [{l2}] ({len(l1)}/{len(l2)}) {'OK' if ok else 'BAD'}")

    _log("\n--- Fallback tests (truth) ---")
    for tc in ["hi", "bye", "I love you", "tell me", "who killed you"]:
        r = _generate_fallback(tc, "truth")
        l1, l2 = r["line1"], r["line2"]
        ok = len(l1) <= MAX_LINE and len(l2) <= MAX_LINE
        if not ok:
            all_ok = False
        _log(f"  '{tc}' -> [{l1}] [{l2}] ({len(l1)}/{len(l2)}) {'OK' if ok else 'BAD'}")

    _log("\n--- Parser tests ---")
    parser_tests = [
        ('{"line1":"... you came back","line2":"I missed you"}',
         "... you came back", "I missed you"),
        ('```json\n{"line1":"... hello","line2":"are you there?"}\n```',
         "... hello", "are you there?"),
        ('Here is the JSON:\n```json\n{"line1":"... waiting","line2":"for you"}\n```',
         "... waiting", "for you"),
        ('{"line1":"... text","line2":"more"',
         "... text", "more"),
        ('{"line1":"... broken',
         "... broken", "?"),
        ('{"line1":"... x","line2":"y"} some trailing text',
         "... x", "y"),
        ('{"line1": "``line1`` Ideas"}',
         "... line1 Ideas", "?"),
        ('The player said hi. Here is my response:\n{"line1":"... hello","line2":"are you there?"}',
         "... hello", "are you there?"),
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
