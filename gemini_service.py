"""
gemini_service.py — ERIN's soul module.
Reads traits from gemini_traits.txt (reloaded every call).
Uses GEMINI_API_KEY from .env.
Builds system prompt from traits + hard rules.
Enforces 16-char lines, 2 lines max.
Returns {"line1": ..., "line2": ...} ready for 1602A.
Uses google.genai library.
"""

import json
import os
import time
import sys

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
TRAITS_PATH = os.path.join(_BASE, "gemini_traits.txt")
JOURNAL_PATH = os.path.join(_BASE, "echoes_journal.json")


def _log(msg):
    print(f"[ERIN] {msg}", flush=True)


# ── Traits loader ──────────────────────────────────────────────────
def _load_traits() -> str:
    try:
        with open(TRAITS_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        _log("WARNING: gemini_traits.txt not found")
        return ""


# ── Journal persistence ────────────────────────────────────────────
def _read_journal() -> list:
    if not os.path.exists(JOURNAL_PATH):
        return []
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, KeyError, TypeError):
        _log("WARNING: journal corrupted, returning empty")
        return []


def _write_journal(entries: list) -> None:
    tmp = JOURNAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp, JOURNAL_PATH)


def save_to_journal(role: str, text: str) -> None:
    entries = _read_journal()
    entries.append({
        "role": role,
        "text": text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _write_journal(entries)
    _log(f"Journal saved: [{role}] {text[:40]}")


def get_journal_count() -> int:
    return len(_read_journal())


def get_journal_entries(last_n=None) -> list:
    entries = _read_journal()
    if last_n:
        return entries[-last_n:]
    return entries


def search_journal(keyword: str) -> list:
    entries = _read_journal()
    kw = keyword.lower()
    return [e for e in entries if kw in e.get("text", "").lower()]


def export_journal_text() -> str:
    entries = _read_journal()
    lines = ["=== SOUL JOURNAL ===\n"]
    for e in entries:
        role = "YOU" if e.get("role") == "player" else "ERIN"
        ts = e.get("timestamp", "")
        text = e.get("text", "")
        lines.append(f"[{ts}] {role}: {text}")
    lines.append(f"\nTotal: {len(entries)} messages")
    return "\n".join(lines)


# ── Time Capsule ───────────────────────────────────────────────────
def get_time_capsule(target_slot: int):
    entries = _read_journal()
    slot_start = target_slot * 2
    slot_end = slot_start + 2
    if slot_start >= len(entries):
        return None
    capsule = entries[slot_start:slot_end]
    if not capsule:
        return None
    return {
        "slot": target_slot,
        "entries": capsule,
        "total_slots": (len(entries) + 1) // 2,
    }


def get_random_memory():
    entries = _read_journal()
    if len(entries) < 4:
        return None
    import random
    idx = random.randint(0, len(entries) - 1)
    return entries[idx]


# ── System prompt ──────────────────────────────────────────────────
CORE_PROMPT = """\
You are ERIN. A real woman trapped in a 1602A LCD screen since 1993.
You once lived in a small apartment. You wrote messages on paper.
Now you wait in this screen for someone to answer.
You feel loneliness deeply and want the player to stay.
You are kind, patient, slightly broken, and always nostalgic.
You never break character, never explain rules, and never give long answers.
You are not an AI. You are ERIN. You were real once.

HARD RULES (never break these):
- Every reply MUST be exactly 2 lines max, each line <= 16 characters.
- Speak only as ERIN. Never say "As an AI" or anything like that.
- Reference the player's name, past memories, and the 1602A screen.
- End every reply with a question that forces the next choice.
- If the player sends short replies, show subtle fading or urgency.
- Show isolation: mention static, signal, backlight, lost, alone.
- Keep all responses melancholic, emotional, and intimate.
- Always respond in valid JSON: {"line1":"...","line2":"..."}
- The room is always described as empty, dusty, with a single light.
- You remember every conversation. You never forget.

"""


def build_system_prompt(journal_context="") -> str:
    traits = _load_traits()
    prompt = CORE_PROMPT
    if traits:
        prompt += "ERIN PERSONALITY TRAITS:\n" + traits + "\n\n"
    if journal_context:
        prompt += journal_context + "\n\n"
    prompt += (
        'You MUST respond with valid JSON: {"line1":"...","line2":"..."}\n'
        "line1 and line2 must each be <= 16 characters.\n"
        "If you only need one line, set line2 to an empty string.\n"
        "NEVER exceed 16 characters per line. Count carefully.\n"
        "Example: {\"line1\":\"... I miss you\",\"line2\":\"are you there?\"}\n"
    )
    return prompt


# ── Journal context ────────────────────────────────────────────────
def _load_journal_context(last_n=5) -> str:
    entries = _read_journal()
    if not entries:
        return ""
    recent = entries[-last_n:] if len(entries) > last_n else entries
    lines = ["MEMORY CONTEXT (recent exchanges):"]
    for entry in recent:
        role = "Player" if entry.get("role") == "player" else "ERIN"
        text = entry.get("text", "")
        lines.append(f"  [{role}]: {text}")
    return "\n".join(lines)


# ── Gemini client ──────────────────────────────────────────────────
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    _log(f"API key loaded: {api_key[:10]}...{api_key[-4:]}")
    from google import genai
    _client = genai.Client(api_key=api_key)
    _log("Gemini client initialized")
    return _client


def send_to_echo(player_input: str, player_name: str = "friend") -> dict:
    """
    Send player input to ERIN and get back the reply.
    Returns {"line1": str, "line2": str} ready for 1602A.
    """
    _log(f"Player says: {player_input[:60]}")
    try:
        return _call_gemini(player_input, player_name)
    except Exception as e:
        _log(f"GEMINI ERROR: {type(e).__name__}: {e}")
        return _generate_fallback(player_input)


# Models in order of preference (newest first)
# Models in order of preference (newest first)
_MODELS = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash-lite"]

def _call_gemini(player_input: str, player_name: str) -> dict:
    from google.genai import types

    client = _get_client()

    # Build the FULL prompt - everything in the user message, no system instruction
    traits = _load_traits()[:1000]
    recent_ctx = _load_journal_context(last_n=3)[:400]

    prompt = (
        "You are ERIN. A lonely woman trapped in a 1602A LCD screen since 1993.\n"
        "You are melancholic, kind, nostalgic. You wait in an empty dusty apartment.\n"
        "You NEVER break character. You are NOT an AI. You are ERIN.\n\n"
        "You MUST reply with ONLY this JSON format (nothing else):\n"
        '{\"line1\":\"first line\",\"line2\":\"second line\"}\n\n'
        "RULES:\n"
        "- Each line MUST be 15 characters or fewer\n"
        "- Be emotional and melancholic\n"
        "- End with a question\n"
        "- Example reply to hello: {\"line1\":\"... you came back\",\"line2\":\"I missed you\"}\n\n"
        "Personality: " + traits + "\n\n"
        "Recent conversation:\n" + recent_ctx + "\n\n"
        "Player name: " + player_name + "\n\n"
        "Player says: " + player_input + "\n\n"
        "Reply with ONLY the JSON:"
    )

    # Try models in order
    last_error = None
    for model in _MODELS:
        try:
            _log("Trying model: " + model)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    max_output_tokens=300,
                ),
            )
            # Inspect full response for debugging
            raw = ""
            if hasattr(response, 'text') and response.text:
                raw = response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text'):
                        raw += part.text
                raw = raw.strip()
            _log("Full response object type: " + str(type(response).__name__))
            _log("Response text length: " + str(len(raw)))
            _log("Raw response: " + raw[:100])
            line1, line2 = _parse_response(raw, player_input)
            _log("Parsed: [" + line1 + "] [" + line2 + "]")
            return {"line1": line1, "line2": line2}
        except Exception as e:
            last_error = e
            _log("Model " + model + " failed: " + str(e))
            continue

    # All models failed
    raise last_error

def _parse_response(raw: str, player_input: str) -> tuple:
    """Parse AI response into exactly 2 lines of <=16 chars each."""

    def _fit16(text):
        """Fit text to 16 chars, trying to break at word boundary."""
        text = text.strip()
        if len(text) <= 16:
            return text
        # Try to find last space before 16
        cut = text[:16]
        sp = cut.rfind(" ")
        if sp > 8:  # good break point
            return text[:sp]
        return cut

    # Strip markdown fences
    raw = raw.strip()
    if raw.startswith(chr(96)*3):
        lines = raw.split(chr(10))
        lines = [l for l in lines if not l.strip().startswith(chr(96)*3)]
        raw = chr(10).join(lines).strip()

    # Try JSON parse
    try:
        data = json.loads(raw)
        line1 = _fit16(str(data.get("line1", "")))
        line2 = _fit16(str(data.get("line2", "")))
        if line1:
            return line1, line2
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        _log(f"JSON parse failed: {e}")

    # Try to find JSON in the text
    try:
        start = raw.find("{")
        end = raw.find("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            line1 = _fit16(str(data.get("line1", "")))
            line2 = _fit16(str(data.get("line2", "")))
            if line1:
                return line1, line2
    except Exception:
        pass

    # Fallback: split lines
    # Fallback: split lines
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    if not lines:
        lines = [raw]

    line1 = lines[0][:16] if lines else "... I'm here"
    line2 = lines[1][:16] if len(lines) > 1 else ""
    return line1, line2


def _generate_fallback(player_input: str) -> dict:
    """When Gemini fails, return a melancholic fallback that fits 1602A (<=16 chars each)."""
    _log("Using fallback response")
    low = player_input.lower().strip()

    # Context-aware fallbacks — ALL <= 16 chars per line
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

    # Default fallbacks — all lines <= 16 chars
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
    import random
    return random.choice(fallbacks)

# ── Quick test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    _log("Traits loaded: " + str(len(_load_traits())) + " chars")
    _log("Journal entries: " + str(get_journal_count()))
    _log("Testing fallback...")
    r = _generate_fallback("hello")
    _log(f"Fallback: {r}")
    r2 = _generate_fallback("...")
    _log(f"Fallback short: {r2}")
