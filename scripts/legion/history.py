from __future__ import annotations

import json
from pathlib import Path

HISTORY_FILE = Path.home() / ".config" / "omarchy" / "legion_history.json"
MAX_HISTORY = 30


def update(thermals: dict, fans: dict, gpu: dict) -> dict:
    history = {"temps": [], "fan_rpm": [], "gpu_temp": []}
    if HISTORY_FILE.exists():
        try:
            loaded = json.loads(HISTORY_FILE.read_text())
            if isinstance(loaded, dict):
                history.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass

    history["temps"].append(thermals.get("cpu_package") or 0)
    history["fan_rpm"].append(fans.get("rpm") or 0)
    history["gpu_temp"].append(gpu.get("temp") or 0)
    for key in ("temps", "fan_rpm", "gpu_temp"):
        history[key] = list(history[key])[-MAX_HISTORY:]

    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = HISTORY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(history))
        tmp.replace(HISTORY_FILE)
    except OSError:
        pass
    return history
