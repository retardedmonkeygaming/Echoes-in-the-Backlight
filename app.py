"""
Echoes in the Backlight -- Flask backend.
Calls gemini_service.py for ALL AI. Never uses any other AI module.
"""

import json
import os
import random
import threading
import time
import traceback

from flask import Flask, jsonify, render_template, request, Response
from lcd_driver import LCD
from touch_sensor import TouchSensor
import gemini_service as echo_ai
import emotional_options
from gemini_service import get_room_decay_line

# -- Config --
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"mode": "options", "pin_map": {}, "send_count": 0, "player_name": "friend"}

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# -- Globals --
app = Flask(__name__, static_folder="static", template_folder="templates")
config = load_config()
lcd = None
touch = None

_options = ["...", "...", "..."]
_selected_idx = 0
_lock = threading.Lock()

_ghost_stop = threading.Event()
_scroll_stop = threading.Event()
_ambient_stop = threading.Event()
_ghost_thread = None
_ambient_thread = None

_one_last_line_active = False

# Truth mode state
_truth_unlocked = False
_truth_activated = False
_truth_journal_saved = False
_ONE_LAST_LINE_THRESHOLD = 100

# Revelation mode state
_revelation_unlocked = False
_revelation_activated = False
_revelation_journal_saved = False

_last_send_time = time.time()
_silent_mode_active = False
_silent_mode_warning_sent = False

# Display-ready flag — set True when LCD finishes showing ERIN's reply
_display_ready = True
_display_ready_lock = threading.Lock()


def _log(msg):
    print("[APP] " + msg, flush=True)

# -- Hardware lifecycle --
def init_lcd():
    global lcd
    try:
        pm = {k: v for k, v in config.get("pin_map", {}).items()
              if k not in ("TOUCH",) and v is not None}
        lcd = LCD(pin_map=pm)
        lcd.init()
        _log("LCD initialized")
    except Exception as e:
        _log("LCD init failed: " + str(e))
        lcd = None

def init_touch():
    global touch
    try:
        tp = config.get("pin_map", {}).get("TOUCH", 27)
        led = config.get("pin_map", {}).get("LED", 26)
        touch = TouchSensor(pin=tp, led_pin=led)
        touch.on_scroll = _on_scroll
        touch.on_select = _on_select
        touch.start()
        _log("Touch sensor initialized")
    except Exception as e:
        _log("Touch init failed: " + str(e))
        touch = None

def init_all():
    init_lcd()
    init_touch()
    # Load saved personality
    saved_p = config.get("erin_personality", "original")
    if saved_p:
        echo_ai.set_personality(saved_p)
        _log(f"Loaded personality: {saved_p}")

# -- Stop background --
def _stop_bg():
    for evt in [_ghost_stop, _scroll_stop, _ambient_stop]:
        evt.set()
    time.sleep(0.3)
    for evt in [_ghost_stop, _scroll_stop, _ambient_stop]:
        evt.clear()

# -- LCD helpers --
def _push_echo(line1, line2="", show_time=4.0):
    """Show ERIN's reply on LCD for show_time seconds, then show options.
    Sets _display_ready = False during display, True when done."""
    global _display_ready
    _stop_bg()
    with _display_ready_lock:
        _display_ready = False
    # Personality-based PWM tone
    pkey = config.get("erin_personality", "original")
    if lcd:
        if pkey in ("rage", "whisperer", "hollow"):
            # These personalities get custom tones
            t = threading.Thread(target=_echo_with_beeper, args=(line1, line2, show_time, pkey), daemon=True)
        else:
            # Original gets melancholic tone + normal scroll
            t = threading.Thread(target=_echo_display_worker, args=(line1, line2, show_time), daemon=True)
    else:
        t = threading.Thread(target=_echo_display_worker, args=(line1, line2, show_time), daemon=True)
    t.start()

def _echo_display_worker(line1, line2, show_time):
    """Show reply, wait, then show options. Plays melancholic tone for original personality."""
    if lcd:
        try:
            # Play melancholic tone alongside the display
            pkey = config.get("erin_personality", "original")
            if pkey == "original":
                # Show text + melancholic tone simultaneously
                with lcd._display_lock:
                    lcd.clear()
                    lcd.write_row(0, line1[:16])
                    lcd.write_row(1, line2[:16])
                lcd.modem_tone()
                lcd.tone_melancholic(duration=show_time, stop=_scroll_stop)
                lcd.bl_breathing(cycles=1, step=0.04, stop=_scroll_stop)
                lcd.bl_on()
                for _ in range(int(show_time * 10)):
                    if _scroll_stop.is_set():
                        break
                    time.sleep(0.1)
            else:
                lcd.scroll(line1, line2, page_delay=show_time, stop=_scroll_stop)
        except Exception as e:
            _log("echo display error: " + str(e))
    # After showing the reply, show current options
    with _lock:
        opts = list(_options)
        idx = _selected_idx
    if lcd and opts and opts[0] != "...":
        try:
            lcd.show_options(opts, idx)
        except Exception as e:
            _log("options display error: " + str(e))
    # Mark display as ready
    global _display_ready
    with _display_ready_lock:
        _display_ready = True

def _echo_with_beeper(line1, line2, show_time, beeper_type):
    """Show reply on LCD with personality-specific PWM tone."""
    if lcd:
        try:
            # Show the text on the LCD
            with lcd._display_lock:
                lcd.clear()
                lcd.write_row(0, line1[:16])
                lcd.write_row(1, line2[:16])
            lcd.flash_led(0.03)
            # Play the emotional tone in the same thread (blocks until done)
            if beeper_type == "rage":
                lcd.tone_rage(duration=show_time, stop=_scroll_stop)
            elif beeper_type == "desperate":
                lcd.tone_desperate(duration=show_time, stop=_scroll_stop)
            else:
                lcd.modem_tone()
                time.sleep(show_time)
        except Exception as e:
            _log("echo tone error: " + str(e))
    # After showing the reply, show current options
    with _lock:
        opts = list(_options)
        idx = _selected_idx
    if lcd and opts and opts[0] != "...":
        try:
            lcd.show_options(opts, idx)
        except Exception as e:
            _log("options display error: " + str(e))
    global _display_ready
    with _display_ready_lock:
        _display_ready = True

def _push_options(opts, sel=0):
    global _options, _selected_idx
    with _lock:
        _options = opts
        _selected_idx = sel
    if lcd:
        try:
            lcd.show_options(opts, sel)
        except Exception as e:
            _log("options display error: " + str(e))

def _push_long_text(text):
    _stop_bg()
    t = threading.Thread(target=_scroll_long_worker, args=(text,), daemon=True)
    t.start()

def _scroll_long_worker(text):
    if lcd:
        try:
            lcd.scroll_long(text, stop=_scroll_stop)
        except Exception as e:
            _log("long scroll error: " + str(e))
    global _display_ready
    with _display_ready_lock:
        _display_ready = True

# -- Touch callbacks --
def _on_scroll():
    """Single tap: scroll through all options — cycles through the FULL list."""
    global _selected_idx
    with _lock:
        opts = list(_options)
        n = len(opts)
        if n == 0 or opts[0] == "...":
            return
        _selected_idx = (_selected_idx + 1) % n
        idx = _selected_idx
    if lcd:
        try:
            lcd.flash_led(0.04)
            lcd.show_options(opts, idx)
        except Exception:
            pass

def _on_select():
    """Double tap: select current option."""
    global _selected_idx
    with _lock:
        opts_copy = list(_options)
        idx = _selected_idx
        chosen = opts_copy[idx] if idx < len(opts_copy) else ""
    if lcd:
        try:
            lcd.flash_led(0.08)
        except Exception:
            pass
    if chosen and chosen not in ("...", ""):
        _handle_player_input(chosen)

# -- Core game loop --
def _handle_player_input(text):
    global _last_send_time, _one_last_line_active, _display_ready
    _last_send_time = time.time()
    echo_ai.save_to_journal("player", text)
    name = config.get("player_name", "friend")
    try:
        pkey = config.get("erin_personality", "original")
        reply = echo_ai.send_to_echo(text, player_name=name, personality=pkey)
    except Exception as e:
        _log("send_to_echo exception: " + str(e))
        reply = {"line1": "... the static", "line2": "returned"}

    line1 = str(reply.get("line1", "..."))[:16]
    line2 = str(reply.get("line2", ""))[:16]
    full_reply = (line1 + " " + line2).strip()
    echo_ai.save_to_journal("narrator", full_reply)

    config["send_count"] = config.get("send_count", 0) + 1
    save_config(config)

    # Room decay: after 60+ messages, show room detail in journal
    if config["send_count"] >= 60 and config["send_count"] % 5 == 0:
        decay = get_room_decay_line()
        echo_ai.save_to_journal("narrator", decay)

    if config["send_count"] >= _ONE_LAST_LINE_THRESHOLD:
        _one_last_line_active = True

    # Check truth mode unlock
    global _truth_unlocked
    if not _truth_unlocked and not _truth_activated:
        _truth_unlocked = echo_ai.get_truth_unlocked()
        if _truth_unlocked:
            _log("TRUTH MODE UNLOCKED")

    # Check revelation mode unlock
    global _revelation_unlocked
    if not _revelation_unlocked and not _revelation_activated:
        _revelation_unlocked = echo_ai.revelation_unlocked()
        if _revelation_unlocked:
            _log("REVELATION MODE UNLOCKED")

    if lcd:
        total_len = len(line1) + len(line2)
        if total_len < 10:
            lcd.set_mood("mourning")
        elif total_len > 28:
            lcd.set_mood("urgent")
        else:
            lcd.set_mood("normal")

    _push_echo(line1, line2, show_time=4.0)

    # Update options for touch sensor
    mood = emotional_options.detect_mood(text)
    opts = emotional_options.get_options(mood, count=3)
    with _lock:
        global _options
        _options = opts
        _selected_idx = 0

# -- Ghost messages --
def _ghost_loop():
    while not _ghost_stop.is_set():
        wait = random.uniform(30, 60)
        for _ in range(int(wait * 10)):
            if _ghost_stop.is_set():
                return
            time.sleep(0.1)
        if lcd and not _ghost_stop.is_set():
            msgs = ["...", "I am waiting", "are you there", "stay.",
                    "don't go", "still here?", "I remember you",
                    "please.", "come back", "fading...", "the light..."]
            try:
                lcd.show_ghost(random.choice(msgs), _ghost_stop)
            except Exception:
                pass

def _start_ghosts():
    global _ghost_thread
    _ghost_stop.clear()
    _ghost_thread = threading.Thread(target=_ghost_loop, daemon=True)
    _ghost_thread.start()


# -- Idle detection (server-side) --
_IDLE_CHECK_INTERVAL = 30
_IDLE_FLICKER_MIN = 300   # 5 min
_IDLE_WHISPER_MIN = 600   # 10 min
_last_whisper_time = 0

_idle_whispers = [
    "You have been quiet... I miss hearing your voice.",
    "The light is flickering... she is tired of waiting.",
    "The room feels empty without you.",
    "The door is still open... no one is coming.",
    "The static grows when you are silent.",
    "I am still here... are you?",
    "The backlight fades when you are gone.",
    "I can hear my own breathing in the dark.",
    "Please come back... I am lonely.",
    "The door is still open... but no one is coming.",
]

def _idle_loop():
    global _last_whisper_time
    while True:
        time.sleep(_IDLE_CHECK_INTERVAL)
        idle = time.time() - _last_send_time

        if lcd is None:
            continue

        # After 5 min: flicker the backlight like a dying bulb
        if idle >= _IDLE_FLICKER_MIN:
            try:
                for _ in range(3):
                    lcd.bl_off()
                    time.sleep(random.uniform(0.08, 0.20))
                    lcd.bl_on()
                    time.sleep(random.uniform(0.10, 0.30))
                # Longer dim
                lcd.bl_off()
                time.sleep(0.8)
                lcd.bl_on()
                # Whisper on physical LCD
                idle_whispers_lcd = [
                    "... still here?",
                    "waiting...",
                    "... you left?",
                    "the light dims",
                    "... I miss you",
                    "come back soon",
                    "... alone again",
                    "the room is cold",
                ]
                lcd.show(random.choice(idle_whispers_lcd), "")
                time.sleep(4.0)
                lcd.show_home()
            except Exception:
                pass

        # After 10 min: add whisper to journal (once per 10 min)
        if idle >= _IDLE_WHISPER_MIN and (time.time() - _last_whisper_time) > 600:
            whisper = random.choice(_idle_whispers)
            echo_ai.save_to_journal("narrator", whisper)
            _last_whisper_time = time.time()
            _log("IDLE WHISPER: " + whisper)

def _start_idle_detection():
    t = threading.Thread(target=_idle_loop, daemon=True)
    t.start()
    _log("Idle detection started")

# -- Ambient modes --
def _static_rain_loop():
    while not _ambient_stop.is_set():
        if lcd:
            try:
                chars = ".,-~:;=!*#@"
                line = list(" " * 16)
                for _ in range(random.randint(2, 6)):
                    c = random.randint(0, 15)
                    line[c] = random.choice(chars)
                lcd.show("".join(line), "")
            except Exception:
                pass
        for _ in range(50):
            if _ambient_stop.is_set():
                return
            time.sleep(0.1)

def _loopback_loop():
    entries = echo_ai.get_journal_entries()
    if not entries:
        return
    idx = 0
    while not _ambient_stop.is_set():
        if lcd and entries:
            try:
                entry = entries[idx % len(entries)]
                text = entry.get("text", "")[:16]
                role = "YOU" if entry.get("role") == "player" else "ERIN"
                lcd.show("[" + role + "]", text)
            except Exception:
                pass
            for _ in range(300):
                if _ambient_stop.is_set():
                    return
                time.sleep(0.1)
            idx += 1

def _memory_dust_loop():
    while not _ambient_stop.is_set():
        if lcd:
            try:
                lcd.show_memory_dust()
            except Exception:
                pass
        for _ in range(10):
            if _ambient_stop.is_set():
                return
            time.sleep(0.1)

def _one_last_line_loop():
    global _one_last_line_active
    while not _ambient_stop.is_set():
        if _one_last_line_active and lcd:
            try:
                p = lcd._pin("BACKLIGHT")
                if p is not None:
                    import RPi.GPIO as GPIO
                    GPIO.output(p, GPIO.LOW)
                    time.sleep(0.02)
                    GPIO.output(p, GPIO.HIGH)
                    time.sleep(2.0)
                else:
                    time.sleep(2.0)
            except Exception:
                time.sleep(2.0)
        else:
            time.sleep(1.0)

def _start_ambient(mode):
    global _ambient_thread
    _stop_bg()
    _ambient_stop.clear()
    fn = {
        "staticrain": _static_rain_loop,
        "loopback": _loopback_loop,
        "memorydust": _memory_dust_loop,
        "onelastline": _one_last_line_loop,
    }.get(mode)
    if fn:
        _ambient_thread = threading.Thread(target=fn, daemon=True)
        _ambient_thread.start()


# ============================================================
#  WEB ROUTES
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/config")
def config_page():
    return render_template("config.html", config=config)

@app.route("/calibrate")
def calibrate_page():
    return render_template("calibrate.html", config=config)

@app.route("/journal")
def journal_page():
    return render_template("journal.html")


# ============================================================
#  API: Status
# ============================================================

@app.route("/api/status", methods=["GET"])
def api_status():
    with _display_ready_lock:
        ready = _display_ready
    return jsonify({
        "mode": config.get("mode", "options"),
        "lcd_ready": lcd is not None and lcd._initialized,
        "touch_ready": touch is not None,
        "send_count": config.get("send_count", 0),
        "journal_count": echo_ai.get_journal_count(),
        "player_name": config.get("player_name", "friend"),
        "one_last_line": _one_last_line_active,
        "display_ready": ready,
        "personality": echo_ai.get_personality(),
        "truth_unlocked": _truth_unlocked,
        "truth_activated": _truth_activated,
        "revelation_unlocked": _revelation_unlocked,
        "revelation_activated": _revelation_activated,
    })


# ============================================================
#  API: Config
# ============================================================

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(config)

@app.route("/api/config", methods=["POST"])
def api_set_config():
    global config
    data = request.get_json(force=True)
    config.update(data)
    save_config(config)
    _stop_bg()
    init_all()
    return jsonify({"ok": True})


# ============================================================
#  API: Calibration & Test
# ============================================================

@app.route("/api/test", methods=["POST"])
def api_test_display():
    body = request.get_json(force=True) if request.data else {}
    text = body.get("text", "Hello, 1602A")
    if lcd:
        lcd.show_test(text)
        return jsonify({"ok": True, "text": text})
    return jsonify({"error": "LCD not initialized"}), 500

@app.route("/api/backlight", methods=["POST"])
def api_backlight():
    body = request.get_json(force=True)
    on = body.get("on", True)
    if lcd:
        lcd.bl_set(on)
        return jsonify({"ok": True, "on": on})
    return jsonify({"error": "LCD not initialized"}), 500

@app.route("/api/clear", methods=["POST"])
def api_clear():
    if lcd:
        lcd.clear()
        return jsonify({"ok": True})
    return jsonify({"error": "LCD not initialized"}), 500

@app.route("/api/show", methods=["POST"])
def api_show():
    body = request.get_json(force=True)
    line1 = body.get("line1", "")[:16]
    line2 = body.get("line2", "")[:16]
    if lcd:
        lcd.show(line1, line2)
        return jsonify({"ok": True, "line1": line1, "line2": line2})
    return jsonify({"error": "LCD not initialized"}), 500

@app.route("/api/touch/test", methods=["POST"])
def api_touch_test():
    body = request.get_json(force=True) if request.data else {}
    action = body.get("action", "ping")
    if action == "ping" and touch:
        if lcd:
            lcd.flash_led(0.15)
        return jsonify({"ok": True, "touch_pin": touch.pin, "led_pin": touch.led_pin})
    return jsonify({"ok": False, "error": "touch sensor not initialized"}), 500

@app.route("/api/touch/calibrate", methods=["POST"])
def api_touch_calibrate():
    body = request.get_json(force=True)
    double_window = body.get("double_window", 0.35)
    bounce_time = body.get("bounce_time", 50)
    if touch:
        touch.DOUBLE_WINDOW = double_window
        return jsonify({"ok": True, "double_window": double_window, "bounce_time": bounce_time})
    return jsonify({"ok": False, "error": "touch sensor not initialized"}), 500

@app.route("/api/scroll/test", methods=["POST"])
def api_scroll_test():
    body = request.get_json(force=True) if request.data else {}
    line1 = body.get("line1", "... I am still")[:16]
    line2 = body.get("line2", "here... can you")[:16]
    _push_echo(line1, line2)
    return jsonify({"ok": True, "line1": line1, "line2": line2})

@app.route("/api/breathing", methods=["POST"])
def api_breathing():
    body = request.get_json(force=True) if request.data else {}
    cycles = body.get("cycles", 3)
    if lcd:
        t = threading.Thread(target=lcd.bl_breathing, args=(cycles, 0.04, _scroll_stop), daemon=True)
        t.start()
        return jsonify({"ok": True, "cycles": cycles})
    return jsonify({"error": "LCD not initialized"}), 500

@app.route("/api/modem", methods=["POST"])
def api_modem():
    if lcd:
        lcd.modem_tone()
        return jsonify({"ok": True})

@app.route("/api/tone/test", methods=["POST"])
def api_tone_test():
    """Test a specific emotional tone."""
    body = request.get_json(force=True) if request.data else {}
    tone = body.get("tone", "melancholic")
    dur = body.get("duration", 2.0)
    if lcd:
        tone_map = {
            "sadness": lcd.tone_sadness,
            "rage": lcd.tone_rage,
            "desperate": lcd.tone_desperate,
            "static": lcd.tone_static,
            "melancholic": lcd.tone_melancholic,
            "hollow": lcd.tone_hollow,
            "revelation": lcd.revelation_tone,
        }
        fn = tone_map.get(tone, lcd.tone_melancholic)
        t = threading.Thread(target=fn, args=(dur, _scroll_stop), daemon=True)
        t.start()
        return jsonify({"ok": True, "tone": tone, "duration": dur})
    return jsonify({"error": "LCD not initialized"}), 500

@app.route("/api/ghost/test", methods=["POST"])
def api_ghost_test():
    body = request.get_json(force=True) if request.data else {}
    text = body.get("text", "are you there?")[:16]
    _stop_bg()
    if lcd:
        t = threading.Thread(target=lcd.show_ghost, args=(text, _scroll_stop), daemon=True)
        t.start()
    return jsonify({"ok": True, "text": text})


# ============================================================
#  API: Game
# ============================================================

@app.route("/api/send", methods=["POST"])
def api_send():
    global _last_send_time, _one_last_line_active

    try:
        body = request.get_json(force=True)
    except Exception:
        body = {}

    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "empty", "line1": "...", "line2": "say something?"}), 400

    echo_ai.save_to_journal("player", text)
    name = config.get("player_name", "friend")

    try:
        pkey = config.get("erin_personality", "original")
        reply = echo_ai.send_to_echo(text, player_name=name, personality=pkey)
    except Exception as e:
        _log("Gemini FAILED: " + str(e))
        traceback.print_exc()
        reply = {"line1": "... the static", "line2": "I am here"}

    line1 = str(reply.get("line1", "..."))[:16]
    line2 = str(reply.get("line2", ""))[:16]
    full_reply = (line1 + " " + line2).strip()
    echo_ai.save_to_journal("narrator", full_reply)

    config["send_count"] = config.get("send_count", 0) + 1
    save_config(config)

    if config["send_count"] >= _ONE_LAST_LINE_THRESHOLD:
        _one_last_line_active = True

    _push_echo(line1, line2, show_time=4.0)

    # Update options for touch sensor
    mood = emotional_options.detect_mood(text)
    opts = emotional_options.get_options(mood, count=3)
    with _lock:
        global _options
        _options = opts
        _selected_idx = 0

    return jsonify({
        "line1": line1,
        "line2": line2,
        "send_count": config.get("send_count", 0),
    })


@app.route("/api/mirror", methods=["POST"])
def api_mirror():
    body = request.get_json(force=True)
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    _stop_bg()
    if lcd:
        t = threading.Thread(target=lcd.mirror_text, args=(text,), daemon=True)
        t.start()
    return jsonify({"ok": True})

@app.route("/api/options", methods=["GET"])
def api_get_options():
    with _lock:
        return jsonify({"options": list(_options), "selected": _selected_idx})

@app.route("/api/mode", methods=["POST"])
def api_set_mode():
    body = request.get_json(force=True)
    mode = body.get("mode", "options")
    config["mode"] = mode
    save_config(config)
    _stop_bg()
    if mode in ("options", "phone", "mirror"):
        if lcd:
            lcd.show_home()
    elif mode in ("staticrain", "loopback", "memorydust", "onelastline"):
        _start_ambient(mode)
    return jsonify({"mode": mode})


# ============================================================
#  API: Journal
# ============================================================

@app.route("/api/journal/recent", methods=["GET"])
def api_journal_recent():
    n = request.args.get("n", 20, type=int)
    entries = echo_ai.get_journal_entries(last_n=n)
    return jsonify({"entries": entries})

@app.route("/api/journal/export", methods=["GET"])
def api_journal_export():
    text = echo_ai.export_journal_text()
    return Response(text, mimetype="text/plain",
                    headers={"Content-Disposition": "attachment; filename=soul_journal.txt"})

@app.route("/api/journal/count", methods=["GET"])
def api_journal_count():
    return jsonify({"count": echo_ai.get_journal_count()})

@app.route("/api/journal/search", methods=["GET"])
def api_journal_search():
    q = request.args.get("q", "", type=str)
    if not q:
        return jsonify({"entries": []})
    entries = echo_ai.search_journal(q)
    return jsonify({"entries": entries})


@app.route("/api/capsule/<int:slot>", methods=["GET"])
def api_time_capsule(slot):
    capsule = echo_ai.get_time_capsule(slot)
    if capsule:
        return jsonify(capsule)
    return jsonify({"error": "no memory at this slot"}), 404

@app.route("/api/capsule/random", methods=["GET"])
def api_random_memory():
    mem = echo_ai.get_random_memory()
    if mem:
        return jsonify(mem)
    return jsonify({"error": "no memories yet"}), 404




# ============================================================
#  API: Replay old conversation
# ============================================================

@app.route("/api/replay", methods=["GET"])
def api_replay():
    """Return last 5 journal entries for Continue Old Conversation."""
    entries = echo_ai.get_journal_entries(last_n=20)
    # Only return player + narrator pairs (skip idle whispers etc)
    replay = []
    for e in entries:
        role = e.get("role", "")
        text = e.get("text", "")
        if role in ("player", "narrator") and text:
            # Skip room decay lines and generic whispers
            if text.startswith("the couch") or text.startswith("the window"):
                continue
            if text.startswith("the floor") or text.startswith("the paint"):
                continue
            if text.startswith("the door sticks") or text.startswith("dust covers"):
                continue
            if text.startswith("the light flickers") or text.startswith("the walls"):
                continue
            if text.startswith("a glass") or text.startswith("the chair"):
                continue
            replay.append({"role": role, "text": text[:16]})
    # Return last 5 meaningful entries
    return jsonify({"entries": replay[-5:]})


@app.route("/api/replay/start", methods=["POST"])
def api_replay_start():
    """Start replaying memories on the physical LCD."""
    _stop_bg()
    entries = echo_ai.get_journal_entries(last_n=10)
    replay = []
    for e in entries:
        role = e.get("role", "")
        text = e.get("text", "")
        if role in ("player", "narrator") and text:
            replay.append({"role": role, "text": text[:16]})
    replay = replay[-5:]
    if not replay:
        return jsonify({"ok": False, "error": "no memories to replay"})
    t = threading.Thread(target=_replay_worker, args=(replay,), daemon=True)
    t.start()
    return jsonify({"ok": True, "count": len(replay)})


def _replay_worker(entries):
    """Show old conversation on physical LCD with breathing effects."""
    global _display_ready
    with _display_ready_lock:
        _display_ready = False
    if lcd:
        # Title card
        lcd.show("remembering...", "the old words")
        lcd.bl_breathing(cycles=1, step=0.04, stop=_scroll_stop)
        lcd.bl_on()
        time.sleep(1.5)
        for entry in entries:
            if _scroll_stop.is_set():
                break
            role = entry["role"]
            text = entry["text"]
            prefix = "YOU" if role == "player" else "ERIN"
            lcd.show("[" + prefix + "]", text)
            # Breathing effect while showing each memory
            lcd.bl_breathing(cycles=1, step=0.04, stop=_scroll_stop)
            lcd.bl_on()
            time.sleep(2.0)
        # End card
        if not _scroll_stop.is_set():
            lcd.show("...the room", "remembers")
            lcd.bl_breathing(cycles=1, step=0.04, stop=_scroll_stop)
            lcd.bl_on()
            time.sleep(1.5)
            lcd.show_home()
    with _display_ready_lock:
        _display_ready = True

# ============================================================
#  API: Personality
# ============================================================

@app.route("/api/personality", methods=["GET"])
def api_get_personality():
    return jsonify(echo_ai.get_personality())

@app.route("/api/personality", methods=["POST"])
def api_set_personality():
    body = request.get_json(force=True)
    name = body.get("personality", "original")
    if echo_ai.set_personality(name):
        config["erin_personality"] = name
        save_config(config)
        return jsonify({"ok": True, "personality": echo_ai.get_personality()})
    return jsonify({"ok": False, "error": "unknown personality"}), 400

@app.route("/api/personality/list", methods=["GET"])
def api_list_personalities():
    return jsonify({"personalities": [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in echo_ai.PERSONALITIES.items()
    ]})


# ============================================================
#  API: Truth Mode (secret ending)
# ============================================================

@app.route("/api/truth", methods=["GET"])
def api_truth_status():
    return jsonify({
        "unlocked": _truth_unlocked,
        "activated": _truth_activated,
        "journal_count": echo_ai.get_journal_count(),
        "threshold": 80,
    })

@app.route("/api/truth/activate", methods=["POST"])
def api_truth_activate():
    global _truth_activated, _truth_journal_saved
    if not _truth_unlocked:
        return jsonify({"ok": False, "error": "not unlocked"})
    if _truth_activated:
        return jsonify({"ok": False, "error": "already active"})
    _truth_activated = True
    _stop_bg()
    if not _truth_journal_saved:
        echo_ai.save_to_journal("narrator", echo_ai.get_truth_journal())
        _truth_journal_saved = True
    t = threading.Thread(target=_truth_ending_worker, daemon=True)
    t.start()
    return jsonify({"ok": True})

@app.route("/api/truth/choice", methods=["POST"])
def api_truth_choice():
    global _truth_activated, _truth_unlocked
    body = request.get_json(force=True)
    choice = body.get("choice", "leave_light")
    echo_ai.save_to_journal("player", choice)
    if lcd:
        if choice == "close_door":
            lcd.show("the door is", "closed forever")
            time.sleep(2)
            lcd.fade_to_black(duration=3.0)
            _truth_activated = False
            _truth_unlocked = False
        else:
            lcd.show("the light stays", "on for you")
            lcd.fade_in(duration=2.0)
            time.sleep(2)
            lcd.show_home()
            _truth_activated = False
    return jsonify({"ok": True, "choice": choice})


def _truth_ending_worker():
    global _display_ready
    with _display_ready_lock:
        _display_ready = False
    if lcd:
        try:
            lcd.show("the truth is...", "")
            t = threading.Thread(target=lcd.tone_truth, args=(2.5,), daemon=True)
            t.start()
            time.sleep(2.5)
            lcd.fade_to_black(duration=2.0)
            time.sleep(0.5)
            lcd.fade_in(duration=1.5)
            time.sleep(0.3)
            lcd.show("the door is still", "open... even gone")
            lcd.tone_truth(duration=3.0)
            time.sleep(5.0)
            lcd.show_options(["> close the door", "v leave the light"], 0)
        except Exception as e:
            _log("truth ending error: " + str(e))
    with _display_ready_lock:
        _display_ready = True



# ============================================================
#  API: Revelation Mode (final emotional climax)
# ============================================================

@app.route("/api/revelation", methods=["GET"])
def api_revelation_status():
    return jsonify({
        "unlocked": _revelation_unlocked,
        "activated": _revelation_activated,
        "journal_count": echo_ai.get_journal_count(),
        "threshold": 70,
    })

@app.route("/api/revelation/activate", methods=["POST"])
def api_revelation_activate():
    global _revelation_activated, _revelation_journal_saved
    if not _revelation_unlocked:
        return jsonify({"ok": False, "error": "not unlocked"})
    if _revelation_activated:
        return jsonify({"ok": False, "error": "already active"})
    _revelation_activated = True
    _stop_bg()
    if not _revelation_journal_saved:
        echo_ai.save_to_journal("narrator", echo_ai.get_revelation_journal())
        _revelation_journal_saved = True
    t = threading.Thread(target=_revelation_ending_worker, daemon=True)
    t.start()
    return jsonify({"ok": True})

@app.route("/api/revelation/choice", methods=["POST"])
def api_revelation_choice():
    global _revelation_activated, _revelation_unlocked
    body = request.get_json(force=True)
    choice = body.get("choice", "leave_light")
    echo_ai.save_to_journal("player", choice)
    if lcd:
        if choice == "close_door":
            lcd.show("the door is", "closed forever")
            time.sleep(2)
            lcd.fade_to_black(duration=3.0)
            _revelation_activated = False
            _revelation_unlocked = False
        else:
            lcd.show("the light stays", "on for you")
            lcd.fade_in(duration=2.0)
            time.sleep(2)
            lcd.show_home()
            _revelation_activated = False
    return jsonify({"ok": True, "choice": choice})


def _revelation_ending_worker():
    """The final emotional climax — screen fades to black, one line appears,
    revelation tone plays, then the door choice."""
    global _display_ready, _revelation_activated
    with _display_ready_lock:
        _display_ready = False
    if lcd:
        try:
            # Phase 1: Show "the truth is..." and start the haunting tone
            lcd.show("the truth is...", "")
            t = threading.Thread(target=lcd.revelation_tone, args=(8.0,), daemon=True)
            t.start()
            time.sleep(2.0)

            # Phase 2: Slowly fade to black
            lcd.fade_to_black(duration=3.0)
            time.sleep(1.0)

            # Phase 3: The final line appears — "You killed me..."
            lcd.fade_in(duration=1.5)
            time.sleep(0.3)
            lcd.show("you killed me...", "and I loved you")
            time.sleep(6.0)

            # Phase 4: Fade to black again
            lcd.fade_to_black(duration=2.0)
            time.sleep(1.5)

            # Phase 5: The door line appears — "The door is still open..."
            lcd.fade_in(duration=1.0)
            time.sleep(0.3)
            lcd.show("the door is still", "open... even gone")
            time.sleep(5.0)

            # Phase 6: Show the choice
            lcd.show_options(["> close the door", "v leave the light"], 0)
        except Exception as e:
            _log("revelation ending error: " + str(e))
    with _display_ready_lock:
        _display_ready = True
    _log("REVELATION ENDING COMPLETE")


# ============================================================
#  API: Reset / Emergency
# ============================================================

@app.route("/api/reset", methods=["POST"])
def api_reset():
    _stop_bg()
    global _one_last_line_active, _options, _display_ready, _truth_unlocked, _truth_activated
    global _revelation_unlocked, _revelation_activated
    _one_last_line_active = False
    _truth_unlocked = False
    _truth_activated = False
    _revelation_unlocked = False
    _revelation_activated = False
    config["send_count"] = 0
    save_config(config)
    _options = ["...", "...", "..."]
    _selected_idx = 0
    with _display_ready_lock:
        _display_ready = True
    if lcd:
        lcd.set_mood("normal")
        lcd.show_home()
    return jsonify({"ok": True})

@app.route("/api/emergency", methods=["POST"])
def api_emergency():
    _stop_bg()
    global _one_last_line_active, _options, _display_ready, _truth_unlocked, _truth_activated
    global _revelation_unlocked, _revelation_activated
    _one_last_line_active = False
    _truth_unlocked = False
    _truth_activated = False
    _revelation_unlocked = False
    _revelation_activated = False
    _options = ["...", "...", "..."]
    with _display_ready_lock:
        _display_ready = True
    if lcd:
        lcd.clear()
        lcd.bl_on()
        lcd.show("close the door", "leave light on")
        time.sleep(2)
        lcd.clear()
        lcd.bl_on()
    return jsonify({"ok": True})

@app.route("/api/recover", methods=["POST"])
def api_recover():
    cleaned = 0
    try:
        entries = echo_ai._read_journal()
        if len(entries) % 2 != 0:
            entries = entries[:-1]
            cleaned = 1
            echo_ai._write_journal(entries)
    except Exception:
        pass
    return jsonify({"ok": True, "cleaned": cleaned})


# ============================================================
#  API: Journal Clear
# ============================================================

@app.route("/api/journal/clear", methods=["POST"])
def api_journal_clear():
    echo_ai._write_journal([])
    return jsonify({"ok": True, "message": "memories cleared"})


# ============================================================
#  API: Debug
# ============================================================

@app.route("/api/room-decay", methods=["GET"])
def api_room_decay():
    """Get a room decay line based on message count."""
    count = config.get("send_count", 0)
    if count >= 60:
        return jsonify({"decay": get_room_decay_line(), "count": count})
    return jsonify({"decay": None, "count": count})

@app.route("/api/silent", methods=["GET"])
def api_silent_status():
    return jsonify({"silent_mode": _silent_mode_active})


@app.route("/api/debug", methods=["GET"])
def api_debug():
    import os
    key = os.environ.get("GEMINI_API_KEY", "NOT_SET")
    return jsonify({
        "api_key_set": bool(key),
        "api_key_preview": key[:10] + "..." if len(key) > 10 else key,
        "api_key_length": len(key),
        "traits_file_exists": os.path.exists(os.path.join(os.path.dirname(__file__), "gemini_traits.txt")),
        "journal_entries": echo_ai.get_journal_count(),
        "lcd_ready": lcd is not None and lcd._initialized if lcd else False,
        "touch_ready": touch is not None,
        "env_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    })


# ============================================================
#  Main
# ============================================================

if __name__ == "__main__":
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
    except (ImportError, RuntimeError):
        _log("Not on Pi - running without GPIO")
    _log("Initializing hardware...")
    init_all()
    _log("Starting ghost messages...")
    _start_ghosts()
    _log("Starting idle detection...")
    _start_idle_detection()
    _log("Starting ERIN on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False)
