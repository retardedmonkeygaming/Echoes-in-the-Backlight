"""
HD44780 LCD driver — 4-bit parallel mode via RPi.GPIO bit-banging.
Strict: 16 chars per line, 2 lines max.
Backlight on GPIO 21 (active-low: LOW = on).
Feedback LED on GPIO 26.
"""

import random
import time
import threading

try:
    import RPi.GPIO as GPIO
    _ON_PI = True
except (ImportError, RuntimeError):
    _ON_PI = False

COLS = 16
ROWS = 2


class LCD:
    def __init__(self, pin_map: dict | None = None):
        self.pins = (pin_map or {}).copy()
        self._lock = threading.Lock()
        self._initialized = False
        self._stop = threading.Event()
        self._mood = "normal"

    def _pin(self, name: str):
        p = self.pins.get(name)
        return p if p is not None else None

    # ── low-level bus ───────────────────────────────────────────────
    def _sleep(self, s): time.sleep(s)

    def _write_nibble(self, nibble):
        for i, key in enumerate(("D4", "D5", "D6", "D7")):
            GPIO.output(self.pins[key], (nibble >> i) & 0x01)
        GPIO.output(self.pins["E"], GPIO.HIGH)
        self._sleep(0.0005)
        GPIO.output(self.pins["E"], GPIO.LOW)
        self._sleep(0.0001)

    def _send(self, value, mode):
        GPIO.output(self.pins["RS"], mode)
        GPIO.output(self.pins["RW"], GPIO.LOW)
        self._write_nibble((value >> 4) & 0x0F)
        self._write_nibble(value & 0x0F)

    def _cmd(self, cmd):
        self._send(cmd, 0)
        if cmd in (0x01, 0x02): self._sleep(0.002)

    def _data(self, char): self._send(char, 1)

    # ── backlight (active-low) ──────────────────────────────────────
    def bl_on(self):
        p = self._pin("BACKLIGHT")
        if p is not None and _ON_PI: GPIO.output(p, GPIO.LOW)

    def bl_off(self):
        p = self._pin("BACKLIGHT")
        if p is not None and _ON_PI: GPIO.output(p, GPIO.HIGH)

    def bl_set(self, on): self.bl_on() if on else self.bl_off()

    def bl_pulse(self, on_s=0.3, off_s=0.7):
        self.bl_on(); time.sleep(on_s); self.bl_off(); time.sleep(off_s); self.bl_on()

    def bl_breathing(self, cycles=3, step=0.05, stop=None):
        p = self._pin("BACKLIGHT")
        if p is None or not _ON_PI: return
        for _ in range(cycles):
            for d in range(1, 11):
                if stop and stop.is_set(): return
                GPIO.output(p, GPIO.LOW); time.sleep(d * step)
                GPIO.output(p, GPIO.HIGH); time.sleep((10 - d) * step * 2)
            for d in range(10, 0, -1):
                if stop and stop.is_set(): return
                GPIO.output(p, GPIO.LOW); time.sleep(d * step)
                GPIO.output(p, GPIO.HIGH); time.sleep((10 - d) * step * 2)

    # ── mood backlight ──────────────────────────────────────────────
    def set_mood(self, mood):
        self._mood = mood

    def mood_pulse(self, dur=2.0):
        p = self._pin("BACKLIGHT")
        if p is None or not _ON_PI: return
        end = time.monotonic() + dur
        if self._mood == "urgent":
            while time.monotonic() < end:
                GPIO.output(p, GPIO.LOW); time.sleep(0.1)
                GPIO.output(p, GPIO.HIGH); time.sleep(0.1)
        elif self._mood == "mourning":
            while time.monotonic() < end:
                GPIO.output(p, GPIO.LOW); time.sleep(0.05)
                GPIO.output(p, GPIO.HIGH); time.sleep(0.45)
        else:
            self.bl_breathing(cycles=1, step=0.04)

    # ── feedback ────────────────────────────────────────────────────
    def flash_led(self, dur=0.05):
        p = self._pin("LED")
        if p is not None and _ON_PI:
            GPIO.output(p, GPIO.HIGH); time.sleep(dur); GPIO.output(p, GPIO.LOW)

    def beep(self, dur=0.03):
        p = self._pin("BUZZER")
        if p is not None and _ON_PI:
            GPIO.output(p, GPIO.HIGH); time.sleep(dur); GPIO.output(p, GPIO.LOW)

    def modem_tone(self):
        p = self._pin("BUZZER")
        if p is None or not _ON_PI: return
        for on, off in [(0.008,0.004),(0.006,0.006),(0.010,0.003),
                        (0.005,0.005),(0.008,0.004),(0.012,0.002)]:
            GPIO.output(p, GPIO.HIGH); time.sleep(on)
            GPIO.output(p, GPIO.LOW); time.sleep(off)

    # ── init ────────────────────────────────────────────────────────
    def init(self):
        if not _ON_PI: return
        with self._lock:
            for name in ["RS","RW","E","D4","D5","D6","D7","BACKLIGHT","LED","BUZZER"]:
                p = self._pin(name)
                if p is None: continue
                GPIO.setup(p, GPIO.OUT)
                if name == "BACKLIGHT": GPIO.output(p, GPIO.HIGH)
                else: GPIO.output(p, GPIO.LOW)
            self._sleep(0.05)
            for _ in range(3): self._write_nibble(0x03); self._sleep(0.005)
            self._write_nibble(0x02); self._sleep(0.001)
            self._cmd(0x28); self._cmd(0x0C); self._cmd(0x06); self._cmd(0x01)
            self._sleep(0.002)
            self._initialized = True
            self.bl_on()

    # ── display primitives ──────────────────────────────────────────
    def clear(self):
        if _ON_PI:
            with self._lock: self._cmd(0x01)

    def set_cursor(self, col, row):
        offsets = [0x00, 0x40]
        self._cmd(0x80 | (col + offsets[row if row < 2 else 0]))

    def write_str(self, text):
        with self._lock:
            for ch in text: self._data(ord(ch))

    def write_row(self, row, text):
        self.set_cursor(0, row)
        self.write_str(text.ljust(COLS)[:COLS])

    # ── high-level ──────────────────────────────────────────────────
    def show(self, line0, line1=""):
        self.clear()
        self.write_row(0, line0)
        self.write_row(1, line1)

    def show_home(self):
        self.show("ECHOES IN THE", "BACKLIGHT")

    def show_test(self, text="Hello, 1602A"):
        self.show(text[:COLS], "ECHOES v0.1")
        self.bl_pulse(0.5, 0.5); self.flash_led(0.2); self.beep(0.05)

    def show_options(self, opts, sel=0):
        self.clear()
        for i in range(min(ROWS, len(opts))):
            marker = "> " if i == sel else "  "
            self.write_row(i, marker + opts[i][:COLS-2])

    def show_memory_dust(self):
        """Tiny speck for 5s — visible proof Echo is collecting pieces."""
        row = random.randint(0, 1)
        col = random.randint(0, COLS - 3)
        self.clear()
        self.write_row(row, " " * col + "*" + " " * (COLS - col - 1))
        self.write_row(1 - row, " " * COLS)
        time.sleep(5.0)
        self.clear()

    def show_ghost(self, text, stop=None):
        """Ghost message — flickers in, holds, fades."""
        self.clear()
        self.write_row(0, text[:COLS])
        self.write_row(1, "")
        for _ in range(3):
            if stop and stop.is_set(): return
            self.bl_off(); time.sleep(0.06)
            self.bl_on(); time.sleep(0.04)
        time.sleep(random.uniform(0.8, 2.0))
        if stop and stop.is_set(): return
        for _ in range(4):
            self.bl_off(); time.sleep(0.08)
            self.bl_on(); time.sleep(0.05)

    def show_lost_signal(self):
        self.show("The signal is", "dead.")
        for _ in range(12):
            self.bl_off(); time.sleep(random.uniform(0.05, 0.15))
            self.bl_on(); time.sleep(random.uniform(0.02, 0.08))
        self.bl_on()

    # ── strict 16-char scroll ───────────────────────────────────────
    @staticmethod
    def _chunk(text, width=16):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip() if cur else w
            if len(test) > width:
                if cur: lines.append(cur.ljust(width)[:width])
                cur = w
            else:
                cur = test
        if cur: lines.append(cur.ljust(width)[:width])
        return lines

    def scroll(self, line1, line2, page_delay=3.0, stop=None):
        """
        Display exactly 2 lines, one page at a time.
        line1 and line2 are already ≤16 chars from gemini_service.
        """
        self.show(line1, line2)
        self.modem_tone()
        self.flash_led(0.03)
        # wait with breathing
        self.bl_breathing(cycles=1, step=0.04, stop=stop)
        for _ in range(int(page_delay * 10)):
            if stop and stop.is_set(): return
            time.sleep(0.1)

    def scroll_long(self, text, page_delay=3.0, breathing=True, stop=None, cb=None):
        """For longer text: split into 16-char lines, show 2 at a time."""
        lines = self._chunk(text, COLS)
        pages = [lines[i:i+ROWS] for i in range(0, len(lines), ROWS)]
        if not pages: return
        for idx, page in enumerate(pages):
            if stop and stop.is_set(): return
            pad = [l.ljust(COLS)[:COLS] for l in page]
            while len(pad) < ROWS: pad.append(" " * COLS)
            self.show(pad[0], pad[1])
            if idx == 0: self.modem_tone()
            else: self.beep(0.02)
            self.flash_led(0.03)
            if cb: cb("\n".join(pad), idx)
            if breathing and idx < len(pages) - 1:
                self.bl_breathing(cycles=1, step=0.04, stop=stop)
            else:
                wait = page_delay if idx < len(pages)-1 else page_delay + 1.0
                for _ in range(int(wait * 10)):
                    if stop and stop.is_set(): return
                    time.sleep(0.1)

    # ── mirror typing ───────────────────────────────────────────────
    def mirror_start(self):
        self.clear(); self._mrow = 0; self._mcol = 0

    def mirror_char(self, ch):
        if not _ON_PI: return
        with self._lock:
            self._data(ord(ch))
        self._mcol += 1
        if self._mcol >= COLS:
            self._mrow += 1; self._mcol = 0
            if self._mrow >= ROWS: self._mrow = 0
            self.set_cursor(0, self._mrow)

    def mirror_text(self, text, speed=0.04):
        self.mirror_start()
        for ch in text:
            if ch == "\n":
                self._mrow = min(self._mrow + 1, ROWS - 1)
                self._mcol = 0
                self.set_cursor(0, self._mrow)
                continue
            self.mirror_char(ch)
            time.sleep(speed + (0.02 if ch == " " else 0))

    # ── cleanup ─────────────────────────────────────────────────────
    def cleanup(self):
        self._stop.set()
        if _ON_PI:
            self.bl_off()
            p = self._pin("LED")
            if p is not None: GPIO.output(p, GPIO.LOW)
            GPIO.cleanup()
