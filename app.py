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
_ONE_LAST_LINE_THRESHOLD = 100

_last_send_time = time.time()


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

# -- Stop background --
def _stop_bg():
    for evt in [_ghost_stop, _scroll_stop, _ambient_stop]:
        evt.set()
    # Wait for scroll thread to actually finish
    time.sleep(0.5)
    for evt in [_ghost_stop, _scroll_stop, _ambient_stop]:
        evt.clear()

# -- LCD helpers --
def _push_echo(line1, line2="", show_time=4.0):
    """Show ERIN's reply on LCD for show_time seconds, then show current options."""
    _stop_bg()
    t = threading.Thread(target=_echo_display_worker, args=(line1, line2, show_time), daemon=True)
    t.start()

def _echo_display_worker(line1, line2, show_time):
    """Show reply, wait, then show options — prevents options from overwriting reply."""
    if lcd:
        try:
            lcd.scroll(line1, line2, page_delay=show_time, stop=_scroll_stop)
        except Exception as e:
            _log("echo display error: " + str(e))
    # After showing the reply, show the current options
    with _lock:
        opts = list(_options)
        idx = _selected_idx
    if lcd and opts and opts[0] != "...":
        try:
            lcd.show_options(opts, idx)
        except Exception as e:
            _log("options display error: " + str(e))

def _scroll_worker(line1, line2):
    """Legacy scroll worker — still used by calibrate test."""
    if lcd:
        try:
            lcd.scroll(line1, line2, stop=_scroll_stop)
        except Exception as e:
            _log("scroll error: " + str(e))

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

# -- Touch callbacks --
def _on_scroll():
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
    global _selected_idx
    with _lock:
        chosen = _options[_selected_idx]
    if lcd:
        try:
            lcd.flash_led(0.08)
        except Exception:
            pass
    if chosen not in ("...", ""):
        _handle_player_input(chosen)

# -- Core game loop --
def _handle_player_input(text):
    global _last_send_time, _one_last_line_active
    _last_send_time = time.time()
    echo_ai.save_to_journal("player", text)
    name = config.get("player_name", "friend")
    try:
        reply = echo_ai.send_to_echo(text, player_name=name)
    except Exception as e:
        _log("send_to_echo exception: " + str(e))
        reply = {"line1": "... the static", "line2": "returned"}

    line1 = str(reply.get("line1", "..."))[:16]
    line2 = str(reply.get("line2", ""))[:16]
    full_reply = (line1 + " " + line2).strip()
    echo_ai.save_to_journal("narrator", full_reply)

    config["send_count"] = config.get("send_count", 0) + 1
    save_config(config)

    if config["send_count"] >= _ONE_LAST_LINE_THRESHOLD:
        _one_last_line_active = True

    if lcd:
        total_len = len(line1) + len(line2)
        if total_len < 10:
            lcd.set_mood("mourning")
        elif total_len > 28:
            lcd.set_mood("urgent")
        else:
            lcd.set_mood("normal")

    _push_echo(line1, line2, show_time=5.0)

    # Update options for touch sensor (LCD shows them after reply)
    mood = emotional_options.detect_mood(text)
    opts = emotional_options.get_options(mood, count=3)
    with _lock:
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
_IDLE_CHECK_INTERVAL = 30   # seconds between checks
_IDLE_FLICKER_MIN = 300     # 5 minutes
_IDLE_WHISPER_MIN = 600     # 10 minutes
_last_whisper_time = 0

_idle_whispers = [
    "You have been quiet... I miss hearing your voice.",
    "The light is flickering... I think she is tired of waiting.",
    "The room feels empty without you.",
    "I left the door open... no one is coming.",
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
                # 3 soft flickers — like a tired heartbeat
                for _ in range(3):
                    lcd.bl_off()
                    time.sleep(random.uniform(0.08, 0.20))
                    lcd.bl_on()
                    time.sleep(random.uniform(0.10, 0.30))
                # Longer dim — she's tired
                lcd.bl_off()
                time.sleep(0.8)
                lcd.bl_on()
                # Show a whisper on the physical LCD too
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

        # After 10 min: add a whisper to the journal (once per 10 min)
        if idle >= _IDLE_WHISPER_MIN and (time.time() - _last_whisper_time) > 600:
            whisper = random.choice(_idle_whispers)
            echo_ai.save_to_journal("narrator", whisper)
            _last_whisper_time = time.time()
            _log(f"IDLE WHISPER: {whisper}")

def _start_idle_detection():
    t = threading.Thread(target=_idle_loop, daemon=True)
    t.start()
    _log("Idle detection started")

# -- Ambient modes --
def _static_rain_loop():
    import random as rng
    while not _ambient_stop.is_set():
        if lcd:
            try:
                chars = ".,-~:;=!*#@"
                line = list(" " * 16)
                for _ in range(rng.randint(2, 6)):
                    c = rng.randint(0, 15)
                    line[c] = rng.choice(chars)
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
#  WEB ROUTES -- Pages
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
    return jsonify({
        "mode": config.get("mode", "options"),
        "lcd_ready": lcd is not None and lcd._initialized,
        "touch_ready": touch is not None,
        "send_count": config.get("send_count", 0),
        "journal_count": echo_ai.get_journal_count(),
        "player_name": config.get("player_name", "friend"),
        "one_last_line": _one_last_line_active,
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

    _last_send_time = time.time()
    echo_ai.save_to_journal("player", text)
    name = config.get("player_name", "friend")

    try:
        reply = echo_ai.send_to_echo(text, player_name=name)
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

    _push_echo(line1, line2, show_time=5.0)

    # Also update options for touch sensor (but don't push to LCD immediately)
    mood = emotional_options.detect_mood(text)
    opts = emotional_options.get_options(mood, count=3)
    with _lock:
        global _options
        _options = opts
        _selected_idx = 0

    return jsonify({
        "line1": line1,
        "line2": line2,
        "options": opts,
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
#  API: Journal (Phase 3)
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
#  API: Reset / Emergency
# ============================================================

@app.route("/api/reset", methods=["POST"])
def api_reset():
    _stop_bg()
    global _one_last_line_active, _options
    _one_last_line_active = False
    config["send_count"] = 0
    save_config(config)
    _options = ["...", "...", "..."]
    _selected_idx = 0
    if lcd:
        lcd.set_mood("normal")
        lcd.show_home()
    return jsonify({"ok": True})

@app.route("/api/emergency", methods=["POST"])
def api_emergency():
    _stop_bg()
    global _one_last_line_active, _options
    _one_last_line_active = False
    _options = ["...", "...", "..."]
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
