"""
Touch sensor — GPIO 27.
Single tap  → scroll (advance option highlight)
Double tap  → confirm / select current option
LED flash on GPIO 26 for every tap.
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

    def start(self):
        if not _ON_PI: return
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        if self.led_pin is not None:
            GPIO.setup(self.led_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.add_event_detect(self.pin, GPIO.RISING,
                              callback=self._edge, bouncetime=50)

    def stop(self):
        if not _ON_PI: return
        GPIO.remove_event_detect(self.pin)
        with self._lock:
            if self._timer: self._timer.cancel()
            self._timer = None
            self._state = _State.IDLE

    def _edge(self, ch):
        self._led_flash()
        with self._lock:
            if self._state == _State.MAYBE_DOUBLE:
                self._cancel(); self._state = _State.IDLE
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
        if self._timer: self._timer.cancel(); self._timer = None

    def _timeout(self):
        with self._lock:
            self._timer = None
            if self._state == _State.MAYBE_DOUBLE:
                self._state = _State.IDLE
                self._fire(self.on_scroll)

    def _fire(self, cb):
        if cb: threading.Thread(target=cb, daemon=True).start()

    def _led_flash(self):
        if self.led_pin is None or not _ON_PI: return
        GPIO.output(self.led_pin, GPIO.HIGH)
        time.sleep(0.04)
        GPIO.output(self.led_pin, GPIO.LOW)

    def cleanup(self):
        self.stop()
