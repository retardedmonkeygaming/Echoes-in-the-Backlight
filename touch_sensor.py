"""
Touch sensor — GPIO 27.
Single tap  -> scroll (advance option highlight)
Double tap  -> confirm / select current option
LED flash on GPIO 26 for every tap.
Falls back to polling if edge detection fails.
"""

import time
import threading
from enum import Enum, auto

try:
    import RPi.GPIO as GPIO
    _ON_PI = True
except (ImportError, RuntimeError):
    _ON_PI = False


class _State(Enum):
    IDLE = auto()
    MAYBE_DOUBLE = auto()


class TouchSensor:
    DOUBLE_WINDOW = 0.35

    def __init__(self, pin=27, led_pin=26):
        self.pin = pin
        self.led_pin = led_pin
        self._state = _State.IDLE
        self._timer = None
        self._lock = threading.Lock()
        self.on_scroll = None
        self.on_select = None
        self._use_polling = False
        self._poll_thread = None
        self._poll_stop = threading.Event()

    def start(self):
        if not _ON_PI:
            return
        # Clean up any stale state
        try:
            GPIO.remove_event_detect(self.pin)
        except Exception:
            pass
        time.sleep(0.05)

        # Ensure pin is set as INPUT
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        if self.led_pin is not None:
            GPIO.setup(self.led_pin, GPIO.OUT, initial=GPIO.LOW)

        # Try edge detection first
        try:
            GPIO.add_event_detect(
                self.pin, GPIO.RISING,
                callback=self._edge, bouncetime=50
            )
            print(f"[Touch] Edge detection active on GPIO{self.pin}")
            return
        except RuntimeError:
            print(f"[Touch] Edge detection failed on GPIO{self.pin}, using polling")
            self._use_polling = True
            self._start_polling()

    def _start_polling(self):
        """Fallback: poll the pin state every 20ms."""
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        last = GPIO.input(self.pin)
        while not self._poll_stop.is_set():
            time.sleep(0.02)
            try:
                cur = GPIO.input(self.pin)
            except Exception:
                continue
            if cur == GPIO.HIGH and last == GPIO.LOW:
                self._edge(self.pin)
            last = cur

    def stop(self):
        self._poll_stop.set()
        if not _ON_PI:
            return
        try:
            GPIO.remove_event_detect(self.pin)
        except Exception:
            pass
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._state = _State.IDLE

    def _edge(self, ch):
        self._led_flash()
        with self._lock:
            if self._state == _State.MAYBE_DOUBLE:
                self._cancel()
                self._state = _State.IDLE
                self._fire(self.on_select)
            else:
                self._state = _State.MAYBE_DOUBLE
                self._start()

    def _start(self):
        self._cancel()
        self._timer = threading.Timer(self.DOUBLE_WINDOW, self._timeout)
        self._timer.daemon = True
        self._timer.start()

    def _cancel(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _timeout(self):
        with self._lock:
            self._timer = None
            if self._state == _State.MAYBE_DOUBLE:
                self._state = _State.IDLE
                self._fire(self.on_scroll)

    def _fire(self, cb):
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def _led_flash(self):
        if self.led_pin is None or not _ON_PI:
            return
        try:
            GPIO.output(self.led_pin, GPIO.HIGH)
            time.sleep(0.04)
            GPIO.output(self.led_pin, GPIO.LOW)
        except Exception:
            pass

    def cleanup(self):
        self.stop()
