"""
Soul Journal — persistent memory for the AI relationship.
SQLite-backed: every input + reply saved with timestamp, lock flag, slot index.
Supports: memory search, lock/unlock, context loading, export, crash recovery.
"""

import os
import sqlite3
import time
from datetime import datetime


class SoulJournal:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "soul_journal.db")

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.DB_PATH
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                slot        INTEGER NOT NULL,
                role        TEXT NOT NULL,          -- 'player' or 'narrator'
                text        TEXT NOT NULL,
                locked      INTEGER DEFAULT 0,      -- 0=unlocked, 1=locked
                created_at  TEXT NOT NULL,
                session_id  TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_slot ON memories(slot);
            CREATE INDEX IF NOT EXISTS idx_locked ON memories(locked);
        """)
        self._conn.commit()

    # ── save ────────────────────────────────────────────────────────

    def save(self, role: str, text: str, slot: int | None = None,
             locked: bool = False, session_id: str = "") -> int:
        """
        Append a memory entry. Returns the new row id.
        If slot is None, auto-assigns next slot number.
        """
        if slot is None:
            row = self._conn.execute("SELECT COALESCE(MAX(slot), 0) + 1 FROM memories").fetchone()
            slot = row[0]
        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO memories (slot, role, text, locked, created_at, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (slot, role, text, int(locked), now, session_id),
        )
        self._conn.commit()
        return cur.lastrowid

    def save_pair(self, player_text: str, narrator_text: str,
                  session_id: str = "") -> tuple[int, int]:
        """Save a player input + narrator reply as a slot pair."""
        row = self._conn.execute("SELECT COALESCE(MAX(slot), 0) + 1 FROM memories").fetchone()
        slot = row[0]
        pid = self.save("player", player_text, slot=slot, session_id=session_id)
        nid = self.save("narrator", narrator_text, slot=slot, session_id=session_id)
        return pid, nid

    # ── lock / unlock ───────────────────────────────────────────────

    def lock(self, slot: int) -> None:
        self._conn.execute("UPDATE memories SET locked = 1 WHERE slot = ?", (slot,))
        self._conn.commit()

    def unlock(self, slot: int) -> None:
        self._conn.execute("UPDATE memories SET locked = 0 WHERE slot = ?", (slot,))
        self._conn.commit()

    def toggle_lock(self, slot: int) -> bool:
        """Toggle lock. Returns new locked state."""
        row = self._conn.execute(
            "SELECT locked FROM memories WHERE slot = ? LIMIT 1", (slot,)
        ).fetchone()
        if row is None:
            return False
        new_state = 0 if row["locked"] else 1
        self._conn.execute(
            "UPDATE memories SET locked = ? WHERE slot = ?", (new_state, slot)
        )
        self._conn.commit()
        return bool(new_state)

    # ── read ────────────────────────────────────────────────────────

    def get_recent(self, n: int = 5) -> list[dict]:
        """Get the last N slot-pairs (most recent first)."""
        rows = self._conn.execute(
            "SELECT DISTINCT slot FROM memories ORDER BY slot DESC LIMIT ?", (n,)
        ).fetchall()
        results = []
        for r in rows:
            slot_rows = self._conn.execute(
                "SELECT * FROM memories WHERE slot = ? ORDER BY id", (r["slot"],)
            ).fetchall()
            results.append({
                "slot": r["slot"],
                "entries": [dict(row) for row in slot_rows],
            })
        return results

    def get_locked(self) -> list[dict]:
        """Get all locked memories."""
        rows = self._conn.execute(
            "SELECT DISTINCT slot FROM memories WHERE locked = 1 ORDER BY slot"
        ).fetchall()
        results = []
        for r in rows:
            slot_rows = self._conn.execute(
                "SELECT * FROM memories WHERE slot = ? ORDER BY id", (r["slot"],)
            ).fetchall()
            results.append({
                "slot": r["slot"],
                "entries": [dict(row) for row in slot_rows],
            })
        return results

    def get_slot(self, slot: int) -> dict | None:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE slot = ? ORDER BY id", (slot,)
        ).fetchall()
        if not rows:
            return None
        return {"slot": slot, "entries": [dict(r) for r in rows]}

    def get_slot_range(self, start: int, end: int) -> list[dict]:
        """Get slots in range [start, end] for loopback mode."""
        rows = self._conn.execute(
            "SELECT DISTINCT slot FROM memories WHERE slot BETWEEN ? AND ? ORDER BY slot",
            (start, end),
        ).fetchall()
        results = []
        for r in rows:
            slot_rows = self._conn.execute(
                "SELECT * FROM memories WHERE slot = ? ORDER BY id", (r["slot"],)
            ).fetchall()
            results.append({
                "slot": r["slot"],
                "entries": [dict(row) for row in slot_rows],
            })
        return results

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(DISTINCT slot) FROM memories").fetchone()
        return row[0]

    def total_sends(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE role = 'player'"
        ).fetchone()
        return row[0]

    # ── context for AI ──────────────────────────────────────────────

    def build_context(self, last_n: int = 5) -> str:
        """
        Build a context string for the AI system prompt:
        last N slot-pairs + all locked memories.
        """
        parts = []

        recent = self.get_recent(last_n)
        if recent:
            parts.append("RECENT MEMORY (last few exchanges):")
            for mem in reversed(recent):
                for e in mem["entries"]:
                    label = "Player" if e["role"] == "player" else "Narrator"
                    parts.append(f"  [{label}]: {e['text']}")
                parts.append("")

        locked = self.get_locked()
        if locked:
            parts.append("LOCKED MEMORIES (the player chose to preserve these forever):")
            for mem in locked:
                for e in mem["entries"]:
                    label = "Player" if e["role"] == "player" else "Narrator"
                    parts.append(f"  [{label}]: {e['text']}")
                parts.append("")

        return "\n".join(parts) if parts else ""

    # ── search ──────────────────────────────────────────────────────

    def search(self, keyword: str) -> list[dict]:
        """Find memories containing keyword."""
        rows = self._conn.execute(
            "SELECT DISTINCT slot FROM memories WHERE text LIKE ? ORDER BY slot",
            (f"%{keyword}%",),
        ).fetchall()
        results = []
        for r in rows:
            slot_rows = self._conn.execute(
                "SELECT * FROM memories WHERE slot = ? ORDER BY id", (r["slot"],)
            ).fetchall()
            results.append({
                "slot": r["slot"],
                "entries": [dict(row) for row in slot_rows],
            })
        return results

    # ── random old memory (echo trigger) ────────────────────────────

    def random_old(self, exclude_slot: int | None = None) -> dict | None:
        """Pick a random memory from the past — for Echo Trigger."""
        if exclude_slot is not None:
            row = self._conn.execute(
                "SELECT DISTINCT slot FROM memories WHERE slot != ? "
                "ORDER BY RANDOM() LIMIT 1", (exclude_slot,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT DISTINCT slot FROM memories ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self.get_slot(row["slot"])

    # ── export ──────────────────────────────────────────────────────

    def export_text(self) -> str:
        """Export entire journal as readable text — like backing up a love letter."""
        rows = self._conn.execute(
            "SELECT DISTINCT slot FROM memories ORDER BY slot"
        ).fetchall()
        lines = ["═══ ECHOES IN THE BACKLIGHT — SOUL JOURNAL ═══\n"]
        for r in rows:
            slot_rows = self._conn.execute(
                "SELECT * FROM memories WHERE slot = ? ORDER BY id", (r["slot"],)
            ).fetchall()
            lines.append(f"─── Memory Slot {r['slot']} ───")
            for entry in slot_rows:
                lock_mark = " 🔒" if entry["locked"] else ""
                ts = entry["created_at"]
                role = entry["role"].upper()
                lines.append(f"  [{ts}] {role}: {entry['text']}{lock_mark}")
            lines.append("")
        lines.append(f"Total memory slots: {len(rows)}")
        lines.append("═══════════════════════════════════════════")
        return "\n".join(lines)

    # ── crash recovery ──────────────────────────────────────────────

    def get_last_slot(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(slot), 0) FROM memories"
        ).fetchone()
        return row[0]

    def is_slot_empty(self, slot: int) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE slot = ?", (slot,)
        ).fetchone()
        return row[0] == 0

    def cleanup_incomplete(self) -> int:
        """
        Remove orphaned slots (only player or only narrator, not both).
        Returns number of slots cleaned.
        """
        rows = self._conn.execute("""
            SELECT slot,
                   SUM(CASE WHEN role='player' THEN 1 ELSE 0 END) as p,
                   SUM(CASE WHEN role='narrator' THEN 1 ELSE 0 END) as n
            FROM memories GROUP BY slot
        """).fetchall()
        cleaned = 0
        for r in rows:
            if (r["p"] > 0) != (r["n"] > 0):  # XOR — one exists but not the other
                self._conn.execute("DELETE FROM memories WHERE slot = ?", (r["slot"],))
                cleaned += 1
        if cleaned:
            self._conn.commit()
        return cleaned

    def close(self) -> None:
        self._conn.close()
