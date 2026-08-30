"""
game_engine.py — Thin wrapper around gemini_service.py.
This file exists for backward compatibility.
ALL AI goes through gemini_service.py. This module just delegates.
"""

import gemini_service as echo_ai


class GameEngine:
    """Legacy wrapper. Delegates everything to gemini_service."""

    def __init__(self, api_key: str = "", model_name: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def send(self, player_input: str, journal_context: str = "",
             echo_memory: str = "", mourning: bool = False) -> dict:
        """Delegate to gemini_service.send_to_echo()."""
        name = "friend"
        try:
            import json, os
            cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
            with open(cfg_path) as f:
                name = json.load(f).get("player_name", "friend")
        except Exception:
            pass
        reply = echo_ai.send_to_echo(player_input, player_name=name)
        return {
            "narration": (reply["line1"] + " " + reply["line2"]).strip(),
            "line1": reply["line1"],
            "line2": reply["line2"],
            "options": ["...", "...", "..."],
            "echo_used": False,
            "mourning": mourning,
        }

    def reset(self):
        pass
