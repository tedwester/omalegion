"""Small persisted plugin state (overnight charge, GPU OC preference)."""

from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = Path.home() / ".config" / "omarchy" / "legion_state.json"
DEFAULTS = {
    "overnight": False,
    "overnight_hold_applied": False,
    "gpu_oc": False,
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
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged))
    tmp.replace(STATE_FILE)
