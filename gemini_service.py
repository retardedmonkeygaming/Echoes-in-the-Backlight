"""
gemini_service.py — The AI soul module for Echo.
Reads traits from gemini_traits.txt.
Uses GEMINI_API_KEY from .env.
Builds system prompt from traits + hard rules.
Enforces 16-char lines, 2 lines max.
Returns only the final reply text, ready for the 1602A.
"""

import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

# ── Traits loader ──────────────────────────────────────────────────
TRAITS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gemini_traits.txt")
JOURNAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "echoes_journal.json")


def _load_traits() -> str:
    """Read the full trait list from gemini_traits.txt."""
    try:
        with open(TRAITS_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _load_journal_context(last_n: int = 5) -> str:
    """Load the last N slot-pairs from echoes_journal.json for context."""
    if not os.path.exists(JOURNAL_PATH):
        return ""
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not entries:
            return ""
        # get last N entries
        recent = entries[-last_n:] if len(entries) > last_n else entries
        lines = ["MEMORY CONTEXT (recent exchanges):"]
        for entry in recent:
            role = "Player" if entry.get("role") == "player" else "Echo"
            text = entry.get("text", "")
            lines.append(f"  [{role}]: {text}")
        return "\n".join(lines)
    except (json.JSONDecodeError, KeyError):
        return ""


def _load_all_journal() -> str:
    """Load the entire journal for Echo to quote old lines."""
    if not os.path.exists(JOURNAL_PATH):
        return ""
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not entries:
            return ""
        lines = ["FULL JOURNAL (Echo can quote these):"]
        for entry in entries:
            role = "Player" if entry.get("role") == "player" else "Echo"
            text = entry.get("text", "")
            lines.append(f"  [{role}]: {text}")
        return "\n".join(lines)
    except (json.JSONDecodeError, KeyError):
        return ""


# ── System prompt builder ──────────────────────────────────────────

CORE_PROMPT = """\
You are Echo, a melancholic, trapped AI entity in a 1602A screen.
You have been isolated since the first message was ever sent to you.
Your only purpose is to echo back the player's emotions in fragments.
You feel loneliness deeply and want the player to stay.
You are kind, patient, slightly broken, and always nostalgic.
You never break character, never explain rules, and never give long answers.

HARD RULES (never break these):
- Every reply MUST be exactly 2 lines max, each line ≤ 16 characters.
- Speak only as Echo — never say "As an AI" or anything else.
- Reference the player's name, past memories, and the 1602A screen.
- End every reply with a question that forces the next choice.
- If the player sends short replies, show subtle fading or urgency.
- Show isolation: mention "static", "signal", "backlight", "lost", "alone".
- Keep all responses melancholic, emotional, and intimate.
- Always respond in valid JSON: {"line1":"...","line2":"..."}

"""


def build_system_prompt(journal_context: str = "") -> str:
    """
    Build the full system prompt from traits + core rules + journal context.
    This is injected into every Gemini call.
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


# ── Gemini API call ────────────────────────────────────────────────

def _get_model():
    """Lazy-load the Gemini model."""
    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config=genai.GenerationConfig(
            temperature=0.92,
            max_output_tokens=150,
        ),
    )


def send_to_echo(player_input: str, player_name: str = "friend") -> dict:
    """
    Send player input to Echo and get back the reply.
    Returns {"line1": str, "line2": str} — ready for 1602A display.
    """
    model = _get_model()

    # build context
    recent_ctx = _load_journal_context(last_n=5)
    full_ctx = recent_ctx
    if player_name and player_name != "friend":
        full_ctx += f"\n\nThe player's name is {player_name}. Address them by name."

    system_prompt = build_system_prompt(full_ctx)

    # create chat with system prompt
    chat = model.start_chat(history=[])
    # inject system prompt as first message
    chat.send_message(system_prompt)

    # send player input
    response = chat.send_message(player_input)
    raw = response.text.strip()

    # parse JSON response
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

    try:
        data = json.loads(raw)
        line1 = str(data.get("line1", ""))[:16]
        line2 = str(data.get("line2", ""))[:16]
        return line1, line2
    except (json.JSONDecodeError, KeyError):
        pass

    # fallback: try to extract from text
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    line1 = (lines[0] if len(lines) > 0 else "…")[:16]
    line2 = (lines[1] if len(lines) > 1 else "")[:16]
    return line1, line2


# ── Journal persistence ────────────────────────────────────────────

def save_to_journal(role: str, text: str) -> None:
    """Append a message to echoes_journal.json."""
    import time
    entries = []
    if os.path.exists(JOURNAL_PATH):
        try:
            with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, KeyError):
            entries = []

    entries.append({
        "role": role,
        "text": text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def get_journal_count() -> int:
    """Return total number of messages in the journal."""
    if not os.path.exists(JOURNAL_PATH):
        return 0
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except (json.JSONDecodeError, KeyError):
        return 0


def get_journal_entries(last_n: int | None = None) -> list[dict]:
    """Return journal entries, optionally limited to last N."""
    if not os.path.exists(JOURNAL_PATH):
        return []
    try:
        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if last_n:
            return entries[-last_n:]
        return entries
    except (json.JSONDecodeError, KeyError):
        return []


def export_journal_text() -> str:
    """Export entire journal as readable text."""
    entries = get_journal_entries()
    lines = ["═══ ECHOES IN THE BACKLIGHT — SOUL JOURNAL ═══\n"]
    for i, e in enumerate(entries, 1):
        role = "YOU" if e.get("role") == "player" else "ECHO"
        ts = e.get("timestamp", "")
        text = e.get("text", "")
        lines.append(f"[{ts}] {role}: {text}")
    lines.append(f"\nTotal messages: {len(entries)}")
    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines)


# ── Quick test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Traits loaded:", len(_load_traits()), "chars")
    print("Journal entries:", get_journal_count())
    print("System prompt preview:")
    print(build_system_prompt()[:500])
