#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capabilities as caps_probe  # noqa: E402

from legion import (  # noqa: E402
    deactivate_dgpu,
    get_battery,
    get_fans,
    get_fullspeed,
    get_gpu,
    get_gsync,
    get_input,
    get_lighting,
    get_power,
    get_system,
    get_thermals,
    install_privileged,
    set_backlight,
    set_battery_mode,
    set_fan_mode,
    set_fan_point,
    set_fan_speed,
    set_flip_to_start,
    set_fn_lock,
    set_fullspeed,
    set_gpu_mode,
    set_gpu_oc,
    set_gsync,
    set_keyboard_brightness,
    set_keyboard_effect,
    set_keyboard_keys,
    set_keyboard_param,
    set_keyboard_power,
    set_keyboard_profile,
    set_microphone_mute,
    set_overnight,
    set_power,
    set_ppt,
    set_speaker_mute,
    set_speaker_volume,
    set_touchpad_lock,
    set_usb_charging,
    update_history,
)
from legion.battery import BATTERY_MODES, apply_overnight_policy  # noqa: E402


def collect_all() -> dict:
    system = get_system()
    power = get_power()
    fans = get_fans()
    thermals = get_thermals()
    gpu = get_gpu()
    battery = get_battery()
    # Explicit overnight policy step (nightly hold / morning restore). This
    # is the only poll-time write; get_battery() itself stays read-only.
    # apply_overnight_policy() is idempotent: it writes at most once per
    # day/night transition.
    applied = apply_overnight_policy(
        BATTERY_MODES.get(battery.get("mode"), {}).get("sysfs")
    )
    if applied:
        battery = get_battery()
    controls = get_input()
    lighting = get_lighting()
    history = update_history(thermals, fans, gpu)
    try:
        caps = caps_probe.collect()
    except Exception:
        caps = {}
    return {
        "system": system,
        "power": power,
        "fans": fans,
        "thermals": thermals,
        "gpu": gpu,
        "battery": battery,
        "input": controls,
        "lighting": lighting,
        "history": history,
        "caps": caps,
    }


def _flag(value: str) -> bool:
    return value.lower() in ("1", "true", "on", "yes")


def _to_int(value: str) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


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
        level = _to_int(arg)
        if level is None:
            return {"status": "error", "message": "Bad backlight level"}
        return set_backlight(level)
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
        percent = _to_int(arg)
        if percent is None:
            return {"status": "error", "message": "Bad fan speed"}
        return set_fan_speed(percent)
    if action == "--set-fan-point" and arg and arg2:
        index = _to_int(arg)
        level = _to_int(arg2)
        if index is None or level is None:
            return {"status": "error", "message": "Bad fan curve point"}
        return set_fan_point(index, level)
    if action == "--set-fullspeed" and arg:
        return set_fullspeed(_flag(arg))
    if action == "--set-gsync" and arg:
        return set_gsync(_flag(arg))
    if action == "--set-kbd-power" and arg:
        return set_keyboard_power(_flag(arg))
    if action == "--set-kbd-brightness" and arg:
        level = _to_int(arg)
        if level is None:
            return {"status": "error", "message": "Bad brightness"}
        return set_keyboard_brightness(level)
    if action == "--set-kbd-slot" and arg:
        slot = _to_int(arg)
        if slot is None:
            return {"status": "error", "message": "Bad lighting slot"}
        return set_keyboard_profile(slot)
    if action == "--set-kbd-effect" and arg:
        color = argv[2] if len(argv) > 2 else None
        try:
            speed = int(argv[3]) if len(argv) > 3 else None
            direction = int(argv[4]) if len(argv) > 4 else None
        except (TypeError, ValueError):
            return {"status": "error", "message": "Bad speed or direction"}
        return set_keyboard_effect(arg, color, speed, direction)
    if action == "--set-kbd-keys" and arg and arg2:
        return set_keyboard_keys([int(x) for x in arg.split(",")[:512] if x.strip().isdigit()], arg2)
    if action == "--set-kbd-speed" and arg:
        try:
            return set_keyboard_param(speed=int(arg))
        except (TypeError, ValueError):
            return {"status": "error", "message": "Bad speed"}
    if action == "--set-kbd-direction" and arg:
        try:
            return set_keyboard_param(direction=int(arg))
        except (TypeError, ValueError):
            return {"status": "error", "message": "Bad direction"}
    if action == "--set-touchpad" and arg:
        return set_touchpad_lock(_flag(arg))
    if action == "--set-mic-mute" and arg:
        return set_microphone_mute(_flag(arg))
    if action == "--set-speaker-mute" and arg:
        return set_speaker_mute(_flag(arg))
    if action == "--set-speaker-volume" and arg:
        percent = _to_int(arg)
        if percent is None:
            return {"status": "error", "message": "Bad volume"}
        return set_speaker_volume(percent)
    if action == "--set-flip-to-start" and arg:
        return set_flip_to_start(_flag(arg))
    if action == "--install-privileged":
        return install_privileged()
    return {"status": "error", "message": f"Unknown action: {action}"}


def main() -> None:
    if len(sys.argv) > 1:
        try:
            print(json.dumps(dispatch(sys.argv[1:])))
        except Exception as exc:
            print(json.dumps({"status": "error", "message": f"Engine error: {exc}"}))
        return
    print(json.dumps(collect_all(), indent=2))


if __name__ == "__main__":
    main()
