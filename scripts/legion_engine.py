#!/usr/bin/env python3
"""Legion Toolkit hardware engine — CLI for the Omarchy plugin."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from legion import (  # noqa: E402
    deactivate_dgpu,
    get_battery,
    get_fans,
    get_gpu,
    get_input,
    get_power,
    get_system,
    get_thermals,
    set_backlight,
    set_battery_mode,
    set_fan_mode,
    set_fan_speed,
    set_fn_lock,
    set_gpu_mode,
    set_gpu_oc,
    set_overnight,
    set_power,
    set_ppt,
    set_usb_charging,
    update_history,
)


def collect_all() -> dict:
    system = get_system()
    power = get_power()
    fans = get_fans()
    thermals = get_thermals()
    gpu = get_gpu()
    battery = get_battery()
    controls = get_input()
    history = update_history(thermals, fans, gpu)
    return {
        "system": system,
        "power": power,
        "fans": fans,
        "thermals": thermals,
        "gpu": gpu,
        "battery": battery,
        "input": controls,
        "history": history,
        "timestamp": time.strftime("%H:%M:%S"),
    }


def _flag(value: str) -> bool:
    return value.lower() in ("1", "true", "on", "yes")


def dispatch(argv: list[str]) -> dict:
    action = argv[0]
    arg = argv[1] if len(argv) > 1 else None
    arg2 = argv[2] if len(argv) > 2 else None

    if action == "--set-power" and arg:
        return set_power(arg)
    if action == "--set-ppt" and arg and arg2:
        return set_ppt(arg, arg2)
    if action == "--set-battery-mode" and arg:
        return set_battery_mode(arg)
    if action == "--set-overnight" and arg:
        return set_overnight(_flag(arg))
    if action == "--set-usb-charging" and arg:
        return set_usb_charging(_flag(arg))
    if action == "--set-fn-lock" and arg:
        return set_fn_lock(_flag(arg))
    if action == "--set-backlight" and arg:
        return set_backlight(int(arg))
    if action == "--set-gpu-mode" and arg:
        return set_gpu_mode(arg)
    if action == "--deactivate-dgpu":
        force = arg and arg.lower() in ("1", "true", "force", "kill", "yes")
        return deactivate_dgpu(kill_processes=force)
    if action == "--set-gpu-oc" and arg:
        return set_gpu_oc(_flag(arg))
    if action == "--set-fan-mode" and arg:
        return set_fan_mode(arg.lower() in ("auto", "1", "true"))
    if action == "--set-fan-speed" and arg:
        return set_fan_speed(int(arg))
    return {"status": "error", "message": f"Unknown action: {action}"}


def main() -> None:
    if len(sys.argv) > 1:
        print(json.dumps(dispatch(sys.argv[1:])))
        return
    print(json.dumps(collect_all(), indent=2))


if __name__ == "__main__":
    main()
