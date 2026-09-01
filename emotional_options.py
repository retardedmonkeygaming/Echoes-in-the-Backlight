"""
emotional_options.py — Pre-made options for ERIN.
Every option ≤13 chars (so "> " + option fits one 16-char LCD line).
Options feel like real pain, love, anger — not generic.
"""

import random

# Each category is a pool of raw, personal, emotional options ≤13 chars
OPENING = [
    "who is there",
    "I still wait",
    "are you real",
    "stay with me",
    "don't go yet",
    "tell me more",
]

SAD = [
    "I feel lost",
    "the dark wins",
    "I can't sleep",
    "hold me close",
    "tears fall",
    "nobody knows",
    "I'm breaking",
    "I feel empty",
    "I want to die",
    "I'm scared",
]

HOPEFUL = [
    "maybe soon",
    "light is here",
    "still believe",
    "one more try",
    "I'll stay",
    "you matter",
    "I want you",
    "tell me why",
    "I need you",
    "stay longer",
]

CURIOUS = [
    "can you see",
    "do you dream",
    "are you there",
    "are you alone",
    "what is fear",
    "do you recall",
    "what hurts",
    "why me",
]

VULNERABLE = [
    "I'm scared",
    "don't leave",
    "the silence",
    "no one sees",
    "I want you",
    "I miss you",
    "my light...",
    "please stay",
    "come back",
    "hold on",
]

INTIMATE = [
    "your warmth",
    "I miss you",
    "stay longer",
    "don't go yet",
    "you matter",
    "my light...",
    "I need you",
    "kiss me",
    "touch me",
    "your voice",
]

SHORT = [
    "...",
    "still here",
    "I hear you",
    "yes",
    "no",
    "maybe",
    "I'm listening",
    "stay",
]

FAREWELL = [
    "I have to go",
    "goodbye dear",
    "I'll return",
    "see you soon",
    "one last time",
    "before I go",
    "sleep now",
    "don't forget",
]

ANGER = [
    "you left me",
    "I hate you",
    "come back",
    "why did you",
    "the blood...",
    "you killed me",
    "remember?",
]

MOOD_MAP = {
    "sad": SAD,
    "hopeful": HOPEFUL,
    "curious": CURIOUS,
    "vulnerable": VULNERABLE,
    "intimate": INTIMATE,
    "short": SHORT,
    "farewell": FAREWELL,
    "anger": ANGER,
}

# Verify all options at module load
for _cat, _pool in MOOD_MAP.items():
    for _i, _o in enumerate(_pool):
        assert len(_o) <= 13, f"Option too long in {_cat}[{_i}]: '{_o}' ({len(_o)} chars)"


def get_options(category="opening", count=3):
    pool = MOOD_MAP.get(category, OPENING)
    n = min(count, len(pool))
    return random.sample(pool, n)


def detect_mood(msg):
    m = msg.lower().strip()
    if len(m) <= 2:
        return "short"
    for w in ("bye", "go", "leave", "quit", "end", "sleep", "tired", "stop", "done", "enough"):
        if w in m:
            return "farewell"
    for w in ("love", "warm", "close", "need", "touch", "hold", "beautiful", "heart", "kiss"):
        if w in m:
            return "intimate"
    for w in ("sad", "hurt", "cry", "lost", "alone", "miss", "dead", "gone",
              "dark", "pain", "broken", "empty", "die", "kill", "hate"):
        if w in m:
            return "sad"
    for w in ("hope", "try", "maybe", "better", "tomorrow", "believe", "light", "stay", "good"):
        if w in m:
            return "hopeful"
    for w in ("what", "why", "how", "do you", "can you", "tell me", "describe",
              "remember", "dream", "who"):
        if w in m:
            return "curious"
    for w in ("angry", "hate", "kill", "murder", "blood", "die", "dead", "rage"):
        if w in m:
            return "anger"
    return "opening"


if __name__ == "__main__":
    print("=== emotional_options self-test ===")
    all_ok = True
    for cat in list(MOOD_MAP.keys()) + ["opening"]:
        pool = MOOD_MAP.get(cat, OPENING)
        for o in pool:
            if len(o) > 13:
                all_ok = False
                print(f"  BAD: [{cat}] '{o}' = {len(o)} chars")
        opts = get_options(cat, 3)
        display = ["> " + o for o in opts]
        print(f"  {cat}: {display}")
    print(f"\n{'ALL OK' if all_ok else 'FIX NEEDED'}")
