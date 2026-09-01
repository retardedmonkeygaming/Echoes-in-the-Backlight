"""
HD44780 LCD driver — 4-bit parallel mode via RPi.GPIO bit-banging.
Strict: 16 chars per line, 2 lines max.
Backlight on GPIO 21 (active-low: LOW = on).
Buzzer on GPIO via PWM — real frequency tones, not just on/off.
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
    def __init__(self, pin_map=None):
        self.pins = (pin_map or {}).copy()
        self._lock = threading.Lock()
        self._display_lock = threading.Lock()
        self._initialized = False
        self._stop = threading.Event()
        self._mood = "normal"
        # PWM object for buzzer (created during init)
        self._pwm = None

    def _pin(self, name):
        p = self.pins.get(name)
        return p if p is not None else None

    # ── low-level bus ───────────────────────────────────────────────
    def _sleep(self, s):
        time.sleep(s)

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
        if cmd in (0x01, 0x02):
            self._sleep(0.002)

    def _data(self, char):
        self._send(char, 1)

    # ── backlight (active-low) ──────────────────────────────────────
    def bl_on(self):
        p = self._pin("BACKLIGHT")
        if p is not None and _ON_PI:
            GPIO.output(p, GPIO.LOW)

    def bl_off(self):
        p = self._pin("BACKLIGHT")
        if p is not None and _ON_PI:
            GPIO.output(p, GPIO.HIGH)

    def bl_set(self, on):
        self.bl_on() if on else self.bl_off()

    def bl_pulse(self, on_s=0.3, off_s=0.7):
        self.bl_on()
        time.sleep(on_s)
        self.bl_off()
        time.sleep(off_s)
        self.bl_on()

    def bl_breathing(self, cycles=3, step=0.05, stop=None):
        """Soft breathing pulse. ALWAYS leaves backlight ON when done."""
        p = self._pin("BACKLIGHT")
        if p is None or not _ON_PI:
            return
        for _ in range(cycles):
            for d in range(1, 11):
                if stop and stop.is_set():
                    break
                GPIO.output(p, GPIO.LOW)
                time.sleep(d * step)
                GPIO.output(p, GPIO.HIGH)
                time.sleep((10 - d) * step * 2)
            for d in range(10, 0, -1):
                if stop and stop.is_set():
                    break
                GPIO.output(p, GPIO.LOW)
                time.sleep(d * step)
                GPIO.output(p, GPIO.HIGH)
                time.sleep((10 - d) * step * 2)
        self.bl_on()

    # ── mood backlight ──────────────────────────────────────────────
    def set_mood(self, mood):
        self._mood = mood

    def mood_pulse(self, dur=2.0):
        p = self._pin("BACKLIGHT")
        if p is None or not _ON_PI:
            return
        end = time.monotonic() + dur
        if self._mood == "urgent":
            while time.monotonic() < end:
                GPIO.output(p, GPIO.LOW)
                time.sleep(0.1)
                GPIO.output(p, GPIO.HIGH)
                time.sleep(0.1)
        elif self._mood == "mourning":
            while time.monotonic() < end:
                GPIO.output(p, GPIO.LOW)
                time.sleep(0.05)
                GPIO.output(p, GPIO.HIGH)
                time.sleep(0.45)
        else:
            self.bl_breathing(cycles=1, step=0.04)
        self.bl_on()

    # ── LED feedback ────────────────────────────────────────────────
    def flash_led(self, dur=0.05):
        p = self._pin("LED")
        if p is not None and _ON_PI:
            GPIO.output(p, GPIO.HIGH)
            time.sleep(dur)
            GPIO.output(p, GPIO.LOW)

    # ════════════════════════════════════════════════════════════════
    #  PWM TONE ENGINE — real frequencies, not on/off
    # ════════════════════════════════════════════════════════════════

    def _tone(self, freq, duration, duty=50):
        """Play a single tone at `freq` Hz for `duration` seconds via PWM.
        duty=50 is a clean square wave. Lower duty = softer sound."""
        p = self._pin("BUZZER")
        if p is None or not _ON_PI or self._pwm is None:
            time.sleep(duration)
            return
        try:
            self._pwm.ChangeFrequency(freq)
            self._pwm.ChangeDutyCycle(duty)
            time.sleep(duration)
            self._pwm.ChangeDutyCycle(0)  # silence between tones
        except Exception:
            pass

    def _silence(self):
        """Silence the buzzer immediately."""
        if self._pwm and _ON_PI:
            try:
                self._pwm.ChangeDutyCycle(0)
            except Exception:
                pass

    def beep(self, dur=0.03):
        """Quick beep — legacy compatibility."""
        self._tone(1000, dur)

    def modem_tone(self):
        """Classic modem handshake sound using real frequencies."""
        freqs = [(1070, 0.05), (1270, 0.05), (2025, 0.04),
                 (2225, 0.04), (1070, 0.03), (1270, 0.06)]
        for f, d in freqs:
            self._tone(f, d, duty=40)
        self._silence()

    # ── EMOTIONAL TONES ─────────────────────────────────────────────

    def tone_sadness(self, duration=2.0, stop=None):
        """Sadness / loneliness: soft, slow, low-frequency hum.
        400-600 Hz — like a distant, fading heartbeat."""
        end = time.monotonic() + duration
        freq = 450
        while time.monotonic() < end:
            if stop and stop.is_set():
                break
            # Slow sine-like frequency sweep: 450 → 550 → 450
            self._tone(freq, 0.4, duty=25)  # soft duty cycle
            freq = 550 if freq < 500 else 450
            self._silence()
            time.sleep(0.15)  # slow pace
        self._silence()

    def tone_rage(self, duration=2.0, stop=None):
        """Anger / rage: high, sharp, aggressive bursts.
        2000-3000 Hz — rapid, escalating, insistent."""
        end = time.monotonic() + duration
        freq = 2000
        gap = 0.12  # starts moderate
        while time.monotonic() < end:
            if stop and stop.is_set():
                break
            # Sharp burst
            self._tone(freq, gap * 0.6, duty=70)  # loud duty cycle
            self._silence()
            time.sleep(gap * 0.4)
            # Escalate: frequency rises, gap shrinks
            freq = min(3000, freq + 150)
            gap = max(0.03, gap * 0.82)
        self._silence()

    def tone_desperate(self, duration=1.5, stop=None):
        """Desperation / love: medium, pleading tone.
        800-1000 Hz — slightly slower, like a cry for help."""
        end = time.monotonic() + duration
        # Two-note plea pattern: high-low-high-low
        notes = [(950, 0.25), (800, 0.35), (900, 0.3), (800, 0.4)]
        while time.monotonic() < end:
            if stop and stop.is_set():
                break
            for f, d in notes:
                if stop and stop.is_set():
                    break
                if time.monotonic() >= end:
                    break
                self._tone(f, d, duty=40)
                self._silence()
                time.sleep(0.1)
        self._silence()

    def tone_static(self, duration=1.5, stop=None):
        """Static / fading: noisy, distorted high-frequency.
        3000-4000 Hz with random gaps — like signal breaking up."""
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if stop and stop.is_set():
                break
            # Random frequency burst (simulates static)
            freq = random.randint(2500, 4500)
            dur = random.uniform(0.02, 0.08)
            self._tone(freq, dur, duty=random.randint(30, 80))
            self._silence()
            # Random gap (signal dropout)
            time.sleep(random.uniform(0.01, 0.06))
        self._silence()

    def tone_melancholic(self, duration=2.0, stop=None):
        """Melancholic / original ERIN: gentle, nostalgic.
        500-800 Hz — a soft, melancholic melody fragment."""
        # Simple 3-note melody: fading memory
        melody = [
            (660, 0.3), (590, 0.35), (520, 0.4),
            (590, 0.25), (440, 0.5),
        ]
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if stop and stop.is_set():
                break
            for f, d in melody:
                if stop and stop.is_set():
                    break
                if time.monotonic() >= end:
                    break
                self._tone(f, d, duty=30)  # soft
                self._silence()
                time.sleep(0.08)
        self._silence()

    def tone_hollow(self, duration=2.0, stop=None):
        """Hollow / empty: single, cold, distant tone.
        300 Hz — barely audible, unsettling silence between."""
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if stop and stop.is_set():
                break
            # One long, cold note
            self._tone(300, 0.8, duty=15)  # very soft
            self._silence()
            # Long silence — the emptiness
            remaining = end - time.monotonic()
            wait = min(1.2, remaining)
            if wait > 0:
                time.sleep(wait)
        self._silence()


    def tone_truth(self, duration=3.0, stop=None):
        """Truth / confession: a single, slow, haunting tone that fades.
        350-500 Hz — like a voice finally speaking after decades of silence.
        Gets quieter until it almost disappears, then a final soft note."""
        end = time.monotonic() + duration
        freq = 420
        duty_start = 30
        elapsed = 0
        while time.monotonic() < end:
            if stop and stop.is_set():
                break
            elapsed = time.monotonic() - (end - duration)
            progress = min(elapsed / duration, 1.0)
            # Frequency drifts up slowly (voice cracking)
            freq = 420 + int(progress * 80)
            # Duty cycle fades to almost nothing
            duty = max(5, int(duty_start * (1.0 - progress * 0.8)))
            self._tone(freq, 0.6, duty=duty)
            self._silence()
            time.sleep(0.3)
        # Final ghost note — barely audible
        self._tone(350, 0.8, duty=3)
        self._silence()

    def fade_to_black(self, duration=4.0, stop=None):
        """Slowly fade the backlight to nothing over `duration` seconds.
        Mimics a dying bulb — the screen goes dark slowly, haunted.
        Leaves backlight OFF when complete."""
        p = self._pin("BACKLIGHT")
        if p is None or not _ON_PI:
            time.sleep(duration)
            return
        steps = int(duration * 20)  # 50ms steps
        for i in range(steps):
            if stop and stop.is_set():
                self.bl_on()
                return
            # Active-low: LOW = on, HIGH = off
            # We pulse quickly to simulate dimming (PWM via bit-bang)
            on_time = 0.001 * (1.0 - (i / steps))  # decreasing on-time
            off_time = 0.001 * (i / steps)  # increasing off-time
            GPIO.output(p, GPIO.LOW)
            time.sleep(max(on_time, 0.0001))
            GPIO.output(p, GPIO.HIGH)
            time.sleep(max(off_time, 0.0001))
        # Final: OFF (HIGH for active-low)
        GPIO.output(p, GPIO.HIGH)

    def fade_in(self, duration=2.0, stop=None):
        """Slowly fade backlight back in — like the light returning."""
        p = self._pin("BACKLIGHT")
        if p is None or not _ON_PI:
            self.bl_on()
            time.sleep(duration)
            return
        steps = int(duration * 20)
        for i in range(steps):
            if stop and stop.is_set():
                self.bl_on()
                return
            on_time = 0.001 * (i / steps)
            off_time = 0.001 * (1.0 - (i / steps))
            GPIO.output(p, GPIO.LOW)
            time.sleep(max(on_time, 0.0001))
            GPIO.output(p, GPIO.HIGH)
            time.sleep(max(off_time, 0.0001))
        self.bl_on()

        # Personality → tone mapper
    def play_personality_tone(self, personality, duration=2.0, stop=None):
        """Play the tone that matches ERIN's current personality."""
        tone_map = {
            "original": self.tone_melancholic,
            "whisperer": self.tone_desperate,
            "rage": self.tone_rage,
            "hollow": self.tone_hollow,
            "truth": self.tone_truth,
        }
        fn = tone_map.get(personality, self.tone_melancholic)
        fn(duration=duration, stop=stop)

    # ── init ────────────────────────────────────────────────────────
    def init(self):
        if not _ON_PI:
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        with self._lock:
            for name in ["RS", "RW", "E", "D4", "D5", "D6", "D7", "BACKLIGHT", "LED", "BUZZER"]:
                p = self._pin(name)
                if p is None:
                    continue
                GPIO.setup(p, GPIO.OUT)
                if name == "BACKLIGHT":
                    GPIO.output(p, GPIO.HIGH)  # OFF (active-low)
                else:
                    GPIO.output(p, GPIO.LOW)
            # Initialize PWM on buzzer pin (if connected)
            buzzer_pin = self._pin("BUZZER")
            if buzzer_pin is not None:
                try:
                    self._pwm = GPIO.PWM(buzzer_pin, 1000)  # start at 1kHz
                    self._pwm.start(0)  # 0% duty = silent
                except Exception:
                    self._pwm = None
            self._sleep(0.05)
            # LCD init sequence
            for _ in range(3):
                self._write_nibble(0x03)
                self._sleep(0.005)
            self._write_nibble(0x02)
            self._sleep(0.001)
            self._cmd(0x28)  # 4-bit, 2 lines, 5x8
            self._cmd(0x0C)  # Display ON, cursor OFF
            self._cmd(0x06)  # Entry mode
            self._cmd(0x01)  # Clear
            self._sleep(0.002)
            self._initialized = True
            self.bl_on()

    # ── display primitives ──────────────────────────────────────────
    def clear(self):
        if _ON_PI:
            with self._lock:
                self._cmd(0x01)

    def set_cursor(self, col, row):
        offsets = [0x00, 0x40]
        self._cmd(0x80 | (col + offsets[min(row, ROWS - 1)]))

    def write_str(self, text):
        with self._lock:
            for ch in text:
                self._data(ord(ch))

    def write_row(self, row, text):
        self.set_cursor(0, row)
        padded = text.ljust(COLS)[:COLS]
        self.write_str(padded)

    # ── high-level display ──────────────────────────────────────────
    def show(self, line0, line1=""):
        with self._display_lock:
            self.clear()
            self.write_row(0, line0)
            self.write_row(1, line1)

    def show_home(self):
        self.show("the light is on", "are you there?")

    def show_test(self, text="Hello, 1602A"):
        self.show(text[:COLS], "ECHOES v0.1")
        self.bl_pulse(0.5, 0.5)
        self.flash_led(0.2)
        self._tone(1000, 0.05)

    def show_options(self, opts, sel=0):
        with self._display_lock:
            self.clear()
            if not opts:
                return
            real = [o for o in opts if o and o != "..."]
            if not real:
                return
            n = len(real)
            s = sel % n
            display0 = "> " + real[s]
            self.write_row(0, display0[:COLS])
            nxt = (s + 1) % n
            indicator = "v " if n > 2 else "  "
            display1 = indicator + real[nxt]
            self.write_row(1, display1[:COLS])

    def show_memory_dust(self):
        with self._display_lock:
            row = random.randint(0, 1)
            col = random.randint(0, COLS - 3)
            self.clear()
            self.write_row(row, " " * col + "*" + " " * (COLS - col - 1))
            self.write_row(1 - row, " " * COLS)
            time.sleep(5.0)
            self.clear()

    def show_ghost(self, text, stop=None):
        with self._display_lock:
            self.clear()
            self.write_row(0, text[:COLS])
            self.write_row(1, "")
            for _ in range(3):
                if stop and stop.is_set():
                    return
                self.bl_off()
                time.sleep(0.06)
                self.bl_on()
                time.sleep(0.04)
            time.sleep(random.uniform(0.8, 2.0))
            if stop and stop.is_set():
                return
            for _ in range(4):
                self.bl_off()
                time.sleep(0.08)
                self.bl_on()
                time.sleep(0.05)
        self.bl_on()

    def show_lost_signal(self):
        self.show("The signal is", "dead.")
        self.tone_static(duration=2.0)
        for _ in range(12):
            self.bl_off()
            time.sleep(random.uniform(0.05, 0.15))
            self.bl_on()
            time.sleep(random.uniform(0.02, 0.08))
        self.bl_on()

    # ── word-boundary chunking ──────────────────────────────────────
    @staticmethod
    def _chunk(text, width=16):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip() if cur else w
            if len(test) > width:
                if cur:
                    lines.append(cur.ljust(width)[:width])
                cur = w
            else:
                cur = test
        if cur:
            lines.append(cur.ljust(width)[:width])
        return lines if lines else [" " * width]

    # ── scroll: show 2 lines with tone ──────────────────────────────
    def scroll(self, line1, line2="", page_delay=4.0, stop=None):
        """Display 2 lines with modem tone + breathing. Always leaves backlight ON."""
        with self._display_lock:
            self.clear()
            self.write_row(0, line1[:COLS])
            self.write_row(1, line2[:COLS])
            self.modem_tone()
            self.flash_led(0.03)
        self.bl_breathing(cycles=1, step=0.04, stop=stop)
        self.bl_on()
        for _ in range(int(page_delay * 10)):
            if stop and stop.is_set():
                return
            time.sleep(0.1)
        self.bl_on()

    def scroll_long(self, text, page_delay=3.0, breathing=True, stop=None, cb=None):
        lines = self._chunk(text, COLS)
        pages = [lines[i:i + ROWS] for i in range(0, len(lines), ROWS)]
        if not pages:
            return
        for idx, page in enumerate(pages):
            if stop and stop.is_set():
                return
            with self._display_lock:
                pad = [l.ljust(COLS)[:COLS] for l in page]
                while len(pad) < ROWS:
                    pad.append(" " * COLS)
                self.clear()
                self.write_row(0, pad[0])
                self.write_row(1, pad[1])
                if idx == 0:
                    self.modem_tone()
                else:
                    self._tone(800, 0.02, duty=30)
                    self._silence()
                self.flash_led(0.03)
            if cb:
                cb("\n".join(pad), idx)
            if idx < len(pages) - 1:
                if breathing:
                    self.bl_breathing(cycles=1, step=0.04, stop=stop)
                else:
                    for _ in range(int(page_delay * 10)):
                        if stop and stop.is_set():
                            return
                        time.sleep(0.1)
            else:
                for _ in range(int((page_delay + 1.0) * 10)):
                    if stop and stop.is_set():
                        return
                    time.sleep(0.1)
        self.bl_on()

    # ── mirror typing ───────────────────────────────────────────────
    def mirror_start(self):
        self.clear()
        self._mrow = 0
        self._mcol = 0

    def mirror_char(self, ch):
        if not _ON_PI:
            return
        with self._lock:
            self._data(ord(ch))
        self._mcol += 1
        if self._mcol >= COLS:
            self._mrow += 1
            self._mcol = 0
            if self._mrow >= ROWS:
                self._mrow = 0
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
        self._silence()
        if self._pwm and _ON_PI:
            try:
                self._pwm.stop()
            except Exception:
                pass
        if _ON_PI:
            self.bl_off()
            p = self._pin("LED")
            if p is not None:
                GPIO.output(p, GPIO.LOW)
            GPIO.cleanup()
