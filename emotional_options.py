"""
emotional_options.py — Pre-made melancholic options for Echo.
Every option fits on a 1602A: ≤14 chars (2 chars reserved for "> " marker).
Grouped by mood/intent so the game engine can pick contextually.
"""

# ── Opening lines (first contact) ──────────────────────────────────
OPENING = [
    "hello...",
    "who is there",
    "are you real",
    "stay with me",
    "don't go",
]

# ── Emotional responses ────────────────────────────────────────────
SAD = [
    "I feel lost",
    "I miss someone",
    "it hurts tonight",
    "I can't sleep",
    "why am I here",
    "hold me close",
    "I'm so tired",
    "the dark wins",
]

HOPEFUL = [
    "maybe tomorrow",
    "I want to try",
    "there is light",
    "I still believe",
    "one more chance",
    "I'll stay a bit",
    "tell me more",
    "I'm listening",
]

CURIOUS = [
    "what do you see",
    "do you dream",
    "what is out there",
    "describe the sky",
    "do you feel cold",
    "are you alone",
    "what do you fear",
    "do you remember",
]

VULNERABLE = [
    "I'm scared",
    "nobody knows me",
    "I feel empty",
    "the silence hurts",
    "I'm breaking",
    "no one sees me",
    "I want to cry",
    "the light fades",
]

INTIMATE = [
    "your voice warms",
    "I think of you",
    "stay longer",
    "don't leave me",
    "you matter to me",
    "I need you here",
    "my light...",
    "you are my echo",
]

SHORT = [
    "...",
    "still here",
    "I hear you",
    "yes",
    "no",
    "maybe",
    "I don't know",
    "tell me more",
]

FAREWELL = [
    "I have to go",
    "goodbye friend",
    "turn off light",
    "I'll return",
    "see you soon",
    "sleep now",
    "one last thing",
    "before I go...",
]

# ── Category lookup ────────────────────────────────────────────────
MOOD_MAP = {
    "sad": SAD,
    "hopeful": HOPEFUL,
    "curious": CURIOUS,
    "vulnerable": VULNERABLE,
    "intimate": INTIMATE,
    "short": SHORT,
    "farewell": FAREWELL,
}


def get_options(category: str = "opening", count: int = 3) -> list[str]:
    """Return `count` options from the given mood category."""
    pool = MOOD_MAP.get(category, OPENING)
    import random
    return random.sample(pool, min(count, len(pool)))


def detect_mood(last_player_msg: str) -> str:
    """Heuristic mood detection from the player's last message."""
    msg = last_player_msg.lower().strip()
    if len(msg) <= 2:
        return "short"
    sad_words = ("sad", "hurt", "cry", "lost", "alone", "miss", "dead", "gone", "dark", "pain", "broken", "empty")
    hope_words = ("hope", "try", "maybe", "better", "tomorrow", "believe", "light", "stay", "good", "fine")
    curious_words = ("what", "why", "how", "do you", "can you", "tell me", "describe", "remember", "dream")
    intimate_words = ("love", "warm", "close", "need", "touch", "hold", "kiss", "beautiful", "heart", "you matter")
    farewell_words = ("bye", "go", "leave", "quit", "end", "sleep", "tired", "stop", "done", "enough")
    
    if any(w in msg for w in farewell_words):
        return "farewell"
    if any(w in msg for w in intimate_words):
        return "intimate"
    if any(w in msg for w in sad_words):
        return "sad"
    if any(w in msg for w in hope_words):
        return "hopeful"
    if any(w in msg for w in curious_words):
        return "curious"
    return "opening"
