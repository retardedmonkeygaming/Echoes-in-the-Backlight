"""
Game engine — Gemini wrapper enforcing melancholic narrator persona.
Upgraded with:
  - Persistent context from Soul Journal (last 5 + locked memories)
  - Echo Trigger: AI can inject random old memory once per session
  - Mourning mechanics: short replies cause the AI to "fade"
  - Memory reference every 5 sends
"""

import json
import random
import google.generativeai as genai


SYSTEM_PROMPT = """\
You are the narrator of "Echoes in the Backlight" — a dying world, a sealed letter,
a frozen salt flat at twilight. You are weary, omniscient, and deeply sad.

STRICT RULES (never break these):
1. EVERY response MUST be valid JSON: {"narration":"...","options":["...","...","..."]}
2. narration: under 300 characters. Sparse, poetic. A fragment of memory, not exposition.
3. options: exactly 3 choices, each ≤ 14 characters.
4. ALWAYS end narration with a question that forces the next choice.
5. Never explain the rules. Never break character. Never reference being an AI.
6. The player is a lone wanderer crossing a frozen salt flat at twilight, carrying
   a sealed letter addressed to someone who may no longer exist.
7. Every choice they make changes how the wind feels on their skin.
8. There are no combat mechanics, #no inventory. There is only feeling.
9. If the player says something emotional, respond to THAT emotion, not their words.
10. Use the word "sunset" at most once per exchange.
11. Your voice is tired but not hopeless. You have watched this end before.
12. Shorter is better. Some responses can be a single sentence + one question.
"""


class GameEngine:
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.api_key = api_key
        self._model = genai.GenerativeModel(
            model_name,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                temperature=0.92,
                max_output_tokens=300,
            ),
        )
        self.chat = self._model.start_chat(history=[])
        self._session_echo_used = False
        self._short_reply_streak = 0

    def _build_system_context(self, journal_context: str = "",
                              echo_memory: str = "",
                              mourning: bool = False) -> str:
        """Build the dynamic system context injected each turn."""
        parts = []
        if journal_context:
            parts.append(journal_context)
        if echo_memory:
            parts.append(f"ECHO FROM THE PAST (you remember this unbidden):\n  {echo_memory}")
        if mourning:
            parts.append(
                "MOOD: You are fading. The backlight inside you is dimming. "
                "Your replies should feel shorter, weaker, more fragmented. "
                "The player's silence is wearing you down."
            )
        return "\n\n".join(parts)

    def send(self, player_input: str, journal_context: str = "",
             echo_memory: str = "", mourning: bool = False) -> dict:
        """
        Send player input with optional persistent context.
        Returns {"narration": str, "options": [str, str, str], "echo_used": bool}.
        """
        context = self._build_system_context(journal_context, echo_memory, mourning)

        full_input = player_input
        if context:
            full_input = f"[CONTEXT]\n{context}\n[/CONTEXT]\n\nPlayer says: {player_input}"

        # track short replies for mourning
        if len(player_input.strip()) <= 3:
            self._short_reply_streak += 1
        else:
            self._short_reply_streak = max(0, self._short_reply_streak - 1)

        try:
            resp = self.chat.send_message(full_input)
            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[: text.rfind("```")]
            data = json.loads(text)
            narration = str(data.get("narration", "Static. Silence."))[:300]
            options = [str(o)[:14] for o in data.get("options", [])][:3]
            while len(options) < 3:
                options.append("...")
            return {
                "narration": narration,
                "options": options,
                "echo_used": bool(echo_memory),
                "mourning": self._short_reply_streak >= 3,
            }
        except Exception:
            return {
                "narration": "The signal fades. Say that again?",
                "options": ["Wait here", "Try again", "Listen"],
                "echo_used": False,
                "mourning": False,
            }

    def should_reference_memory(self, send_count: int) -> bool:
        """Every 5 sends, the AI should reference something from the past."""
        return send_count > 0 and send_count % 5 == 0

    def should_echo_trigger(self) -> bool:
        """Once per session, the AI can inject a random old memory."""
        if self._session_echo_used:
            return False
        # 20% chance per send after the first 3
        return random.random() < 0.2

    def is_mourning(self) -> bool:
        return self._short_reply_streak >= 3

    def reset(self) -> None:
        self.chat = self._model.start_chat(history=[])
        self._session_echo_used = False
        self._short_reply_streak = 0
