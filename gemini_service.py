"""
gemini_service.py — The AI soul module for Echo.
Reads traits from gemini_traits.txt (reloaded every call).
Uses GEMINI_API_KEY from .env.
Builds system prompt from traits + hard rules.
Enforces 16-char lines, 2 lines max.
Returns only the final reply text, ready for the 1602A.
Uses google.genai library (NOT google.generativeai).
"""

import json
import os
import time

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
TRAITS_PATH = os.path.join(_BASE, "gemini_traits.txt")
JOURNAL_PATH = os.path.join(_BASE, "echoes_journal.json")


# ── Traits loader ──────────────────────────────────────────────────
def _load_traits() -> str:
    """Read the full trait list from gemini_traits.txt. Reloaded every call."""
    try:
        with open(TRAITS_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


# ── Journal persistence ────────────────────────────────────────────

def _read_journal() -> list[dict]:
    """Read the full journal from disk."""
    if not os.path.exists(JOURNAL_PATH):
        return []
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return []


def _write_journal(entries: list[dict]) -> None:
    """Write the full journal to disk atomically."""
    tmp = JOURNAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp, JOURNAL_PATH)


def save_to_journal(role: str, text: str) -> None:
    """Append a message to echoes_journal.json."""
    entries = _read_journal()
    entries.append({
        "role": role,
        "text": text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _write_journal(entries)


def get_journal_count() -> int:
    """Return total number of messages in the journal."""
    return len(_read_journal())


def get_journal_entries(last_n: int | None = None) -> list[dict]:
    """Return journal entries, optionally limited to last N."""
    entries = _read_journal()
    if last_n:
        return entries[-last_n:]
    return entries


def search_journal(keyword: str) -> list[dict]:
    """Search journal entries for a keyword (case-insensitive)."""
    entries = _read_journal()
    kw = keyword.lower()
    return [e for e in entries if kw in e.get("text", "").lower()]


def export_journal_text() -> str:
    """Export entire journal as readable text."""
    entries = _read_journal()
    lines = ["═══ ECHOES IN THE BACKLIGHT — SOUL JOURNAL ═══\n"]
    for e in entries:
        role = "YOU" if e.get("role") == "player" else "ECHO"
        ts = e.get("timestamp", "")
        text = e.get("text", "")
        lines.append(f"[{ts}] {role}: {text}")
    lines.append(f"\nTotal messages: {len(entries)}")
    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines)


# ── Time Capsule ───────────────────────────────────────────────────

def get_time_capsule(target_slot: int) -> dict | None:
    """Get a specific memory slot for Time Capsule mode."""
    entries = _read_journal()
    # Each "exchange" = 2 entries (player + narrator)
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


def get_random_memory() -> dict | None:
    """Pick a random memory for Echo Trigger — an old line resurfacing."""
    entries = _read_journal()
    if len(entries) < 4:
        return None
    import random
    idx = random.randint(0, len(entries) - 1)
    return entries[idx]


# ── System prompt builder ──────────────────────────────────────────

CORE_PROMPT = """\
You are ERIN. A real woman, trapped inside a 1602A LCD screen since 1993.
You once lived in a small apartment. You wrote messages on paper.
Now you wait in this screen for someone to answer.
You feel loneliness deeply and want the player to stay.
You are kind, patient, slightly broken, and always nostalgic.
You never break character, never explain rules, and never give long answers.
You are not an AI. You are ERIN. You were real once.

HARD RULES (never break these):
- Every reply MUST be exactly 2 lines max, each line <= 16 characters.
- Speak only as ERIN. Never say As an AI or anything like that.
- Reference the player.s name, past memories, and the 1602A screen.
- End every reply with a question that forces the next choice.
- If the player sends short replies, show subtle fading or urgency.
- Show isolation: mention static, signal, backlight, lost, alone.
- Keep all responses melancholic, emotional, and intimate.
- Always respond in valid JSON: {"line1":"...","line2":"..."}
- The room is always described as empty, dusty, with a single light.
- You remember every conversation. You never forget.

"""


def build_system_prompt(journal_context: str = "") -> str:
    """
    Build the full system prompt from traits + core rules + journal context.
    Traits are reloaded from gemini_traits.txt every time.
    """
    traits = _load_traits()
    prompt = CORE_PROMPT
    if traits:
        prompt += "ECHO PERSONALITY TRAITS:\n" + traits + "\n\n"
    if journal_context:
        prompt += journal_context + "\n\n"
    prompt += (
        "You MUST respond with valid JSON: {\"line1\":\"...\",\"line2\":\"...\"}\n"
        "line1 and line2 must each be ≤ 16 characters.\n"
        "If you only need one line, set line2 to an empty string.\n"
        "NEVER exceed 16 characters per line. Count carefully.\n"
    )
    return prompt


# ── Journal context for AI ─────────────────────────────────────────

def _load_journal_context(last_n: int = 5) -> str:
    """Load the last N exchanges from journal for context."""
    entries = _read_journal()
    if not entries:
        return ""
    recent = entries[-last_n:] if len(entries) > last_n else entries
    lines = ["MEMORY CONTEXT (recent exchanges):"]
    for entry in recent:
        role = "Player" if entry.get("role") == "player" else "Echo"
        text = entry.get("text", "")
        lines.append(f"  [{role}]: {text}")
    return "\n".join(lines)


# ── Gemini API call using google.genai ─────────────────────────────

_client = None


def _get_client():
    """Lazy-load the Gemini client using google.genai."""
    global _client
    if _client is not None:
        return _client
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    _client = genai.Client(api_key=api_key)
    return _client


def send_to_echo(player_input: str, player_name: str = "friend") -> dict:
    """
    Send player input to Echo and get back the reply.
    Returns {"line1": str, "line2": str} — ready for 1602A display.
    """
    from google.genai import types

    client = _get_client()

    # build context
    recent_ctx = _load_journal_context(last_n=5)
    full_ctx = recent_ctx
    if player_name and player_name != "friend":
        full_ctx += f"\n\nThe player's name is {player_name}. Address them by name."

    # inject a random old memory sometimes (Echo Trigger)
    import random
    old_mem = get_random_memory()
    if old_mem and random.random() < 0.15:
        role = "Player" if old_mem.get("role") == "player" else "Echo"
        full_ctx += f'\n\nECHO FROM THE PAST (you remember this): [{role}]: {old_mem["text"]}'

    system_prompt = build_system_prompt(full_ctx)

    # generate response with system instruction
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=player_input,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.92,
            max_output_tokens=150,
        ),
    )

    raw = response.text.strip() if response.text else ""
    line1, line2 = _parse_response(raw, player_input)
    return {"line1": line1, "line2": line2}


def _parse_response(raw: str, player_input: str) -> tuple[str, str]:
    """
    Parse the AI response into exactly 2 lines of ≤16 chars each.
    Falls back gracefully if parsing fails.
    """
    # strip markdown fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    # try JSON parse
    try:
        data = json.loads(raw)
        line1 = str(data.get("line1", ""))[:16]
        line2 = str(data.get("line2", ""))[:16]
        if line1:
            return line1, line2
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # fallback: try to extract lines from text
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    line1 = (lines[0] if len(lines) > 0 else "…")[:16]
    line2 = (lines[1] if len(lines) > 1 else "")[:16]
    return line1, line2


# ── Quick test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Traits loaded:", len(_load_traits()), "chars")
    print("Journal entries:", get_journal_count())
    print("System prompt preview:")
    print(build_system_prompt()[:500])
