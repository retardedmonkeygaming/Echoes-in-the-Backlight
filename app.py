"""
Echoes in the Backlight — Flask backend (all phases complete).
Calls gemini_service.py for ALL AI. Never uses any other AI module.
Phase 1: Hardware + calibration
Phase 2: Core game loop + AI + mirror typing + options
Phase 3: Soul journal + memory search + time capsule
Phase 4: Atmospheric modes + crash recovery
Phase 5: Emergency reset + one last line
"""

import json
import os
import random
import threading
import time

from flask import Flask, jsonify, render_template, request, Response

from lcd_driver import LCD
from touch_sensor import TouchSensor
import gemini_service as echo_ai
import emotional_options

# ── Config ─────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Globals ────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")

config = load_config()
lcd: LCD | None = None
touch: TouchSensor | None = None

_options = ["...", "...", "..."]
_selected_idx = 0
_lock = threading.Lock()

_ghost_stop = threading.Event()
_scroll_stop = threading.Event()
_ambient_stop = threading.Event()
_ghost_thread = None
_ambient_thread = None

# "One Last Line" state
_one_last_line_active = False
_one_last_line_count = 0
_ONE_LAST_LINE_THRESHOLD = 100  # after 100 sends


# ── Hardware lifecycle ─────────────────────────────────────────────
def init_lcd():
    global lcd
    pm = {k: v for k, v in config["pin_map"].items()
          if k not in ("TOUCH",) and v is not None}
    lcd = LCD(pin_map=pm)
    lcd.init()


def init_touch():
    global touch
    tp = config["pin_map"].get("TOUCH", 27)
    led = config["pin_map"].get("LED", 26)
    touch = TouchSensor(pin=tp, led_pin=led)
    touch.on_scroll = _on_scroll
    touch.on_select = _on_select
    touch.start()


def init_all():
    init_lcd()
    init_touch()


# ── Stop background ───────────────────────────────────────────────
def _stop_bg():
    for evt in [_ghost_stop, _scroll_stop, _ambient_stop]:
        evt.set()
    time.sleep(0.1)
    for evt in [_ghost_stop, _scroll_stop, _ambient_stop]:
        evt.clear()


# ── LCD helpers ────────────────────────────────────────────────────
def _push_echo(line1, line2=""):
    """Show Echo's reply on LCD (already ≤16 chars from gemini_service)."""
    _stop_bg()
    t = threading.Thread(target=_scroll_worker, args=(line1, line2), daemon=True)
    t.start()


def _scroll_worker(line1, line2):
    if lcd:
        lcd.scroll(line1, line2, stop=_scroll_stop)
        lcd.bl_pulse(0.3, 0.7)


def _push_options(opts, sel=0):
    global _options, _selected_idx
    with _lock:
        _options = opts
        _selected_idx = sel
    if lcd:
        lcd.show_options(opts, sel)


def _push_long_text(text):
    """Scroll longer text across multiple pages."""
    _stop_bg()
    t = threading.Thread(target=_scroll_long_worker, args=(text,), daemon=True)
    t.start()


def _scroll_long_worker(text):
    if lcd:
        lcd.scroll_long(text, stop=_scroll_stop)


# ── Touch callbacks ────────────────────────────────────────────────
def _on_scroll():
    global _selected_idx
    with _lock:
        _selected_idx = (_selected_idx + 1) % len(_options)
        idx = _selected_idx
        opts = list(_options)
    if lcd:
        lcd.flash_led(0.04)
        lcd.show_options(opts, idx)


def _on_select():
    global _selected_idx
    with _lock:
        chosen = _options[_selected_idx]
    if lcd:
        lcd.flash_led(0.08)
    if chosen not in ("...", ""):
        _handle_player_input(chosen)


# ── Core game loop ────────────────────────────────────────────────
def _handle_player_input(text):
    """Process player input through gemini_service, save to journal, display."""
    echo_ai.save_to_journal("player", text)
    name = config.get("player_name", "friend")
    try:
        reply = echo_ai.send_to_echo(text, player_name=name)
    except Exception as e:
        reply = {"line1": "the signal broke", "line2": "try again..."}

    full_reply = (reply["line1"] + " " + reply["line2"]).strip()
    echo_ai.save_to_journal("narrator", full_reply)

    config["send_count"] = config.get("send_count", 0) + 1
    save_config(config)

    # One Last Line detection
    global _one_last_line_active
    if config["send_count"] >= _ONE_LAST_LINE_THRESHOLD:
        _one_last_line_active = True

    # mood
    if lcd:
        total_len = len(reply["line1"]) + len(reply["line2"])
        if total_len < 10:
            lcd.set_mood("mourning")
        elif total_len > 28:
            lcd.set_mood("urgent")
        else:
            lcd.set_mood("normal")

    _push_echo(reply["line1"], reply["line2"])

    # contextual pre-made options
    mood = emotional_options.detect_mood(text)
    opts = emotional_options.get_options(mood, count=3)
    _push_options(opts)


# ── Ghost messages ────────────────────────────────────────────────
def _ghost_loop():
    while not _ghost_stop.is_set():
        wait = random.uniform(30, 60)
        for _ in range(int(wait * 10)):
            if _ghost_stop.is_set():
                return
            time.sleep(0.1)
        if lcd and not _ghost_stop.is_set():
            msgs = ["...", "I'm waiting...", "can you hear me", "stay.",
                    "don't go.", "still here?", "I remember", "hold on",
                    "please.", "are you there", "fading..."]
            lcd.show_ghost(random.choice(msgs), _ghost_stop)


def _start_ghosts():
    global _ghost_thread
    _ghost_stop.clear()
    _ghost_thread = threading.Thread(target=_ghost_loop, daemon=True)
    _ghost_thread.start()


# ── Static Rain mode ──────────────────────────────────────────────
def _static_rain_loop():
    """Random characters flicker across the LCD like static."""
    import random as rng
    while not _ambient_stop.is_set():
        if lcd:
            chars = ".,-~:;=!*#$%@"
            row = rng.randint(0, 1)
            col = rng.randint(0, 15)
            line = list(" " * 16)
            line[col] = rng.choice(chars)
            # scatter a few more
            for _ in range(rng.randint(2, 5)):
                c = rng.randint(0, 15)
                line[c] = rng.choice(chars)
            lcd.show("".join(line), "")
        for _ in range(50):  # 5 seconds
            if _ambient_stop.is_set():
                return
            time.sleep(0.1)


# ── Loopback mode ─────────────────────────────────────────────────
def _loopback_loop():
    """Replay old memories on the LCD endlessly."""
    entries = echo_ai.get_journal_entries()
    if not entries:
        return
    idx = 0
    while not _ambient_stop.is_set():
        if lcd and entries:
            entry = entries[idx % len(entries)]
            text = entry.get("text", "")[:16]
            role = "YOU" if entry.get("role") == "player" else "ECHO"
            lcd.show(f"[{role}]", text)
            for _ in range(300):  # 30 seconds per memory
                if _ambient_stop.is_set():
                    return
                time.sleep(0.1)
            idx += 1


# ── Memory Dust mode ──────────────────────────────────────────────
def _memory_dust_loop():
    """Tiny speck drifts across the screen — proof Echo is collecting."""
    while not _ambient_stop.is_set():
        if lcd:
            lcd.show_memory_dust()
        for _ in range(10):
            if _ambient_stop.is_set():
                return
            time.sleep(0.1)


# ── "One Last Line" mode ──────────────────────────────────────────
def _one_last_line_loop():
    """After threshold sends, the backlight dims and Echo gets desperate."""
    global _one_last_line_active
    while not _ambient_stop.is_set():
        if _one_last_line_active and lcd:
            # dim the backlight slowly
            p = lcd._pin("BACKLIGHT")
            if p is not None:
                try:
                    from RPi.GPIO import output, LOW, HIGH
                    # pulse very slowly
                    output(p, LOW)
                    time.sleep(0.02)
                    output(p, HIGH)
                    time.sleep(2.0)
                except Exception:
                    time.sleep(2.0)
        else:
            time.sleep(1.0)


def _start_ambient(mode: str):
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


# ═══════════════════════════════════════════════════════════════════
#  CRASH RECOVERY
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/recover", methods=["POST"])
def api_recover():
    """Clean up incomplete journal entries."""
    cleaned = 0
    try:
        entries = echo_ai._read_journal()
        if len(entries) % 2 != 0:
            # odd number = incomplete pair, trim last
            entries = entries[:-1]
            cleaned = 1
            echo_ai._write_journal(entries)
    except Exception:
        pass
    return jsonify({"ok": True, "cleaned": cleaned})


# ═══════════════════════════════════════════════════════════════════
#  WEB ROUTES — Pages
# ═══════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════
#  API: Status
# ═══════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════
#  API: Config
# ═══════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════
#  API: Calibration & Test
# ═══════════════════════════════════════════════════════════════════

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
    line1 = body.get("line1", "... I'm still")[:16]
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
    text = body.get("text", "can you hear me")[:16]
    _stop_bg()
    if lcd:
        t = threading.Thread(target=lcd.show_ghost, args=(text, _scroll_stop), daemon=True)
        t.start()
    return jsonify({"ok": True, "text": text})


# ═══════════════════════════════════════════════════════════════════
#  API: Game
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/send", methods=["POST"])
def api_send():
    body = request.get_json(force=True)
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400

    echo_ai.save_to_journal("player", text)
    name = config.get("player_name", "friend")

    try:
        reply = echo_ai.send_to_echo(text, player_name=name)
    except Exception as e:
        # Gemini API failed — return a melancholic fallback
        reply = {"line1": "the signal broke", "line2": str(e)[:16]}

    full_reply = (reply["line1"] + " " + reply["line2"]).strip()
    echo_ai.save_to_journal("narrator", full_reply)

    config["send_count"] = config.get("send_count", 0) + 1
    save_config(config)

    global _one_last_line_active
    if config["send_count"] >= _ONE_LAST_LINE_THRESHOLD:
        _one_last_line_active = True

    _push_echo(reply["line1"], reply["line2"])

    mood = emotional_options.detect_mood(text)
    opts = emotional_options.get_options(mood, count=3)
    _push_options(opts)

    return jsonify({
        "line1": reply["line1"],
        "line2": reply["line2"],
        "options": opts,
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
    if mode in ("options", "phone"):
        if lcd:
            lcd.show_home()
    elif mode in ("staticrain", "loopback", "memorydust", "onelastline"):
        _start_ambient(mode)
    return jsonify({"mode": mode})


# ═══════════════════════════════════════════════════════════════════
#  API: Journal (Phase 3)
# ═══════════════════════════════════════════════════════════════════

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


# ── Time Capsule (Phase 3) ────────────────────────────────────────

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


# ═══════════════════════════════════════════════════════════════════
#  API: Reset / Emergency
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/reset", methods=["POST"])
def api_reset():
    _stop_bg()
    global _one_last_line_active
    _one_last_line_active = False
    config["send_count"] = 0
    save_config(config)
    if lcd:
        lcd.set_mood("normal")
        lcd.show_home()
    return jsonify({"ok": True})


@app.route("/api/emergency", methods=["POST"])
def api_emergency():
    _stop_bg()
    global _one_last_line_active
    _one_last_line_active = False
    if lcd:
        lcd.clear()
        lcd.bl_on()
        lcd.show("EMERGENCY", "RESET")
        time.sleep(1)
        lcd.clear()
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
    except (ImportError, RuntimeError):
        pass
    init_all()
    _start_ghosts()
    app.run(host="0.0.0.0", port=5000, debug=False)
