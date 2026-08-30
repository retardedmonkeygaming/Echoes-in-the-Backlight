"""
Echoes in the Backlight — Flask backend.
Calls gemini_service.py for ALL AI. Never uses game_engine.py or any other AI module.
Phase 1: pin calibration, touch sensor, core game loop.
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
_ghost_thread = None


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
    for evt in [_ghost_stop, _scroll_stop]:
        evt.set()
    time.sleep(0.1)
    for evt in [_ghost_stop, _scroll_stop]:
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
    # save player message
    echo_ai.save_to_journal("player", text)

    # get Echo's reply
    name = config.get("player_name", "friend")
    reply = echo_ai.send_to_echo(text, player_name=name)

    # save Echo's reply
    full_reply = (reply["line1"] + " " + reply["line2"]).strip()
    echo_ai.save_to_journal("narrator", full_reply)

    # update send count
    config["send_count"] = config.get("send_count", 0) + 1
    save_config(config)

    # set mood based on reply length
    if lcd:
        total_len = len(reply["line1"]) + len(reply["line2"])
        if total_len < 10:
            lcd.set_mood("mourning")
        elif total_len > 28:
            lcd.set_mood("urgent")
        else:
            lcd.set_mood("normal")

    # display on LCD
    _push_echo(reply["line1"], reply["line2"])

    # show options for next choice
    _push_options(reply.get("options", ["...", "...", "..."])[:3])


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
    """Show arbitrary 2-line text on LCD."""
    body = request.get_json(force=True)
    line1 = body.get("line1", "")[:16]
    line2 = body.get("line2", "")[:16]
    if lcd:
        lcd.show(line1, line2)
        return jsonify({"ok": True, "line1": line1, "line2": line2})
    return jsonify({"error": "LCD not initialized"}), 500


@app.route("/api/touch/test", methods=["POST"])
def api_touch_test():
    """Register a test callback for touch sensor — returns event info."""
    body = request.get_json(force=True) if request.data else {}
    action = body.get("action", "ping")
    if action == "ping" and touch:
        # flash LED to confirm touch is alive
        if lcd:
            lcd.flash_led(0.15)
        return jsonify({"ok": True, "touch_pin": touch.pin, "led_pin": touch.led_pin})
    return jsonify({"ok": False, "error": "touch sensor not initialized"}), 500


@app.route("/api/touch/calibrate", methods=["POST"])
def api_touch_calibrate():
    """Save touch sensitivity settings."""
    body = request.get_json(force=True)
    double_window = body.get("double_window", 0.35)
    bounce_time = body.get("bounce_time", 50)
    if touch:
        touch.DOUBLE_WINDOW = double_window
        return jsonify({
            "ok": True,
            "double_window": double_window,
            "bounce_time": bounce_time,
        })
    return jsonify({"ok": False, "error": "touch sensor not initialized"}), 500


@app.route("/api/scroll/test", methods=["POST"])
def api_scroll_test():
    """Test scroll display with sample text."""
    body = request.get_json(force=True) if request.data else {}
    line1 = body.get("line1", "... I'm still")[:16]
    line2 = body.get("line2", "here... can you")[:16]
    _push_echo(line1, line2)
    return jsonify({"ok": True, "line1": line1, "line2": line2})


@app.route("/api/breathing", methods=["POST"])
def api_breathing():
    """Test breathing backlight effect."""
    body = request.get_json(force=True) if request.data else {}
    cycles = body.get("cycles", 3)
    if lcd:
        t = threading.Thread(target=lcd.bl_breathing, args=(cycles, 0.04, _scroll_stop), daemon=True)
        t.start()
        return jsonify({"ok": True, "cycles": cycles})
    return jsonify({"error": "LCD not initialized"}), 500


@app.route("/api/modem", methods=["POST"])
def api_modem():
    """Play modem connect tone."""
    if lcd:
        lcd.modem_tone()
        return jsonify({"ok": True})
    return jsonify({"error": "LCD not initialized"}), 500


@app.route("/api/ghost/test", methods=["POST"])
def api_ghost_test():
    """Test ghost message display."""
    body = request.get_json(force=True) if request.data else {}
    text = body.get("text", "can you hear me")[:16]
    _stop_bg()
    t = threading.Thread(target=lcd.show_ghost, args=(text, _scroll_stop), daemon=True) if lcd else None
    if t:
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

    # save player message
    echo_ai.save_to_journal("player", text)

    # get Echo's reply
    name = config.get("player_name", "friend")
    reply = echo_ai.send_to_echo(text, player_name=name)

    # save Echo's reply
    full_reply = (reply["line1"] + " " + reply["line2"]).strip()
    echo_ai.save_to_journal("narrator", full_reply)

    # update count
    config["send_count"] = config.get("send_count", 0) + 1
    save_config(config)

    # display
    _push_echo(reply["line1"], reply["line2"])

    return jsonify(reply)


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
    return jsonify({"mode": mode})


# ═══════════════════════════════════════════════════════════════════
#  API: Journal
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


# ═══════════════════════════════════════════════════════════════════
#  API: Reset / Emergency
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/reset", methods=["POST"])
def api_reset():
    _stop_bg()
    config["send_count"] = 0
    save_config(config)
    if lcd:
        lcd.set_mood("normal")
        lcd.show_home()
    return jsonify({"ok": True})


@app.route("/api/emergency", methods=["POST"])
def api_emergency():
    _stop_bg()
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
    init_all()
    _start_ghosts()
    app.run(host="0.0.0.0", port=5000, debug=False)
