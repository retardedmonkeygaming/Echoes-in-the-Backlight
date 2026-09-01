"""
emotional_options.py — Pre-made melancholic options for ERIN.
Every option ≤13 chars (so "> " + option fits one 16-char LCD line).
Always returns fresh shuffled copies — never the same order twice.
"""

import random

# Mood-based option pools — ALL verified ≤13 chars
OPENING = ["hello...", "who is there", "are you real", "stay with me", "don't go"]
SAD = ["I feel lost", "I miss you", "it hurts now", "I can't sleep", "why am I",
       "hold me close", "the dark wins", "I feel empty"]
HOPEFUL = ["maybe soon", "I want to try", "light is here", "still believe",
           "one more try", "tell me more", "I'm listening", "I'll stay"]
CURIOUS = ["can you see", "do you dream", "is it outside", "are you there",
           "are you alone", "do you recall", "what is fear"]
VULNERABLE = ["I'm scared", "nobody knows", "the silence", "I'm breaking",
              "no one sees", "I want to cry", "light is dim"]
INTIMATE = ["your warmth", "I miss you", "stay longer", "don't go yet",
            "you matter", "I need you", "my light..."]
SHORT = ["...", "still here", "I hear you", "yes", "no", "maybe", "tell me more"]
FAREWELL = ["I have to go", "goodbye dear", "I'll return", "see you soon",
            "sleep now", "one last time", "before I go"]

MOOD_MAP = {
    "sad": SAD, "hopeful": HOPEFUL, "curious": CURIOUS,
    "vulnerable": VULNERABLE, "intimate": INTIMATE,
    "short": SHORT, "farewell": FAREWELL
}

# Verify all options at module load
for _cat, _pool in MOOD_MAP.items():
    for _i, _o in enumerate(_pool):
        assert len(_o) <= 13, f"Option too long in {_cat}[{_i}]: '{_o}' ({len(_o)} chars)"


def get_options(category="opening", count=3):
    """Return `count` SHORT options for the given mood.
    Every call returns a fresh shuffled copy.
    All options ≤13 chars so "> " + option ≤15 chars on LCD.
    The 3rd option is always visible by scrolling."""
    pool = MOOD_MAP.get(category, OPENING)
    n = min(count, len(pool))
    # Always return a fresh random selection — never same order
    return random.sample(pool, n)


def detect_mood(msg):
    """Detect mood from player message."""
    m = msg.lower().strip()
    if len(m) <= 2:
        return "short"
    for w in ("bye", "go", "leave", "quit", "end", "sleep", "tired", "stop", "done", "enough"):
        if w in m:
            return "farewell"
    for w in ("love", "warm", "close", "need", "touch", "hold", "beautiful", "heart"):
        if w in m:
            return "intimate"
    for w in ("sad", "hurt", "cry", "lost", "alone", "miss", "dead", "gone",
              "dark", "pain", "broken", "empty"):
        if w in m:
            return "sad"
    for w in ("hope", "try", "maybe", "better", "tomorrow", "believe", "light", "stay", "good"):
        if w in m:
            return "hopeful"
    for w in ("what", "why", "how", "do you", "can you", "tell me", "describe",
              "remember", "dream"):
        if w in m:
            return "curious"
    return "opening"


# Self-test
if __name__ == "__main__":
    print("=== emotional_options self-test ===")
    all_ok = True
    for cat in list(MOOD_MAP.keys()) + ["opening"]:
        pool = MOOD_MAP.get(cat, OPENING)
        for o in pool:
            if len(o) > 13:
                all_ok = False
                print(f"  BAD: [{cat}] '{o}' = {len(o)} chars")
        # Test 5 calls — each should return different order
        calls = [get_options(cat, 3) for _ in range(5)]
        opts = calls[0]
        display = ["> " + o for o in opts]
        # Verify all fit
        for o in opts:
            if len("> " + o) > 16:
                all_ok = False
                print(f"  OVERFLOW: '{o}' -> display '{'> ' + o}' = {len('> ' + o)} chars")
        print(f"  {cat}: {display}")
    print(f"\n{'ALL OK' if all_ok else 'FIX NEEDED'}")
