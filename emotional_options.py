OPENING = ["hello...", "who is there", "are you real", "stay with me", "don't go"]
SAD = ["I feel lost", "I miss someone", "it hurts tonight", "I can't sleep", "why am I here", "hold me close", "I'm so tired", "the dark wins"]
HOPEFUL = ["maybe tomorrow", "I want to try", "there is light", "I still believe", "one more chance", "I'll stay a bit", "tell me more", "I'm listening"]
CURIOUS = ["what do you see", "do you dream", "what is out there", "describe the sky", "do you feel cold", "are you alone", "what do you fear", "do you remember"]
VULNERABLE = ["I'm scared", "nobody knows me", "I feel empty", "the silence hurts", "I'm breaking", "no one sees me", "I want to cry", "the light fades"]
INTIMATE = ["your voice warms", "I think of you", "stay longer", "don't leave me", "you matter to me", "I need you here", "my light...", "you are my echo"]
SHORT = ["...", "still here", "I hear you", "yes", "no", "maybe", "I don't know", "tell me more"]
FAREWELL = ["I have to go", "goodbye friend", "turn off light", "I'll return", "see you soon", "sleep now", "one last thing", "before I go..."]

MOOD_MAP = {"sad":SAD, "hopeful":HOPEFUL, "curious":CURIOUS, "vulnerable":VULNERABLE, "intimate":INTIMATE, "short":SHORT, "farewell":FAREWELL}

def get_options(category="opening", count=3):
    import random
    pool = MOOD_MAP.get(category, OPENING)
    return random.sample(pool, min(count, len(pool)))

def detect_mood(msg):
    m = msg.lower().strip()
    if len(m) <= 2: return "short"
    for w in ("bye","go","leave","quit","end","sleep","tired","stop","done","enough"):
        if w in m: return "farewell"
    for w in ("love","warm","close","need","touch","hold","beautiful","heart"):
        if w in m: return "intimate"
    for w in ("sad","hurt","cry","lost","alone","miss","dead","gone","dark","pain","broken","empty"):
        if w in m: return "sad"
    for w in ("hope","try","maybe","better","tomorrow","believe","light","stay","good","fine"):
        if w in m: return "hopeful"
    for w in ("what","why","how","do you","can you","tell me","describe","remember","dream"):
        if w in m: return "curious"
    return "opening"