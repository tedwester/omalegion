from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = Path.home() / ".config" / "omarchy" / "legion_state.json"
DEFAULTS = {
    "overnight": False,
    "overnight_hold_applied": False,
    "gpu_oc": False,
    "touchpad_lock": False,
    "fan_manual": False,
    "fan_curve_default": None,
    "fan_percent": None,
    "kbd_brightness": 5,
    "kbd_last": None,
    "last_platform_profile": None,
    "last_ppd": None,
}


def load() -> dict:
    data = dict(DEFAULTS)
    if STATE_FILE.exists():
        try:
            saved = json.loads(STATE_FILE.read_text())
            if isinstance(saved, dict):
                data.update(saved)
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save(data: dict) -> None:
    merged = dict(DEFAULTS)
    merged.update(data)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged))
        tmp.replace(STATE_FILE)
    except OSError:
        pass
