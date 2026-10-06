#!/usr/bin/env python3
"""Legion Toolkit hardware engine — CLI for the Omarchy plugin."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from legion import (  # noqa: E402
    apply_godmode_preset,
    deactivate_dgpu,
    delete_godmode_preset,
    get_battery,
    get_boot_options,
    get_capabilities,
    get_display,
    get_fan_curve,
    get_fans,
    get_gpu,
    get_input,
    get_lighting,
    get_power,
    get_system,
    get_thermals,
    list_godmode_presets,
    restart_dgpu,
    save_godmode_preset,
    set_backlight,
    set_battery_mode,
    set_brightness,
    set_fan_fullspeed,
    set_fan_mode,
    set_fan_point,
    set_fan_speed,
    set_flip_to_start,
    set_fn_lock,
    set_gpu_mode,
    set_gpu_oc,
    set_gpu_oc_delta,
    set_instant_boot,
    set_logo_light,
    set_mic_mute,
    set_overdrive,
    set_overnight,
    set_overnight_window,
    set_ports_light,
    set_power,
    set_ppt,
    set_speaker_mute,
    set_speaker_volume,
    set_touchpad,
    set_usb_charging,
    set_usb_mode,
    set_white_backlight,
    update_history,
)
from legion.battery import tick_battery  # noqa: E402


def collect_all() -> dict:
    system = get_system()
    try:
        capabilities = get_capabilities()
    except Exception:
        capabilities = {}
    power = get_power()
    fans = get_fans()
    thermals = get_thermals()
    gpu = get_gpu()
    battery = get_battery()
    controls = get_input()
    try:
        display = get_display()
    except Exception:
        display = {}
    try:
        lighting = get_lighting()
    except Exception:
        lighting = {}
    try:
        boot = get_boot_options()
    except Exception:
        boot = {}
    # Overnight hold is a maintenance write, kept out of get_battery() reads.
    try:
        tick_battery()
        # Re-read battery so overnight_active reflects the applied hold.
        battery = get_battery()
    except Exception:
        pass
    history = update_history(thermals, fans, gpu)
    return {
        "system": system,
        "capabilities": capabilities,
        "power": power,
        "fans": fans,
        "thermals": thermals,
        "gpu": gpu,
        "battery": battery,
        "input": controls,
        "display": display,
        "lighting": lighting,
        "boot": boot,
        "history": history,
        "timestamp": time.strftime("%H:%M:%S"),
    }


def _flag(value: str) -> bool:
    return str(value).lower() in ("1", "true", "on", "yes")


def _int(value: str | None, name: str) -> int:
    try:
        return int(str(value))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {name}: {value}")


def dispatch(argv: list[str]) -> dict:
    action = argv[0]
    arg = argv[1] if len(argv) > 1 else None
    arg2 = argv[2] if len(argv) > 2 else None
    arg3 = argv[3] if len(argv) > 3 else None
    try:
        return _dispatch(argv, action, arg, arg2, arg3)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}


def _dispatch(argv: list[str], action: str, arg: str | None, arg2: str | None, arg3: str | None) -> dict:

    if action == "--set-power" and arg:
        return set_power(arg)
    if action == "--set-ppt" and arg and arg2:
        return set_ppt(arg, arg2)
    if action == "--save-preset" and arg:
        try:
            values = json.loads(arg2 or "{}")
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid preset JSON"}
        return save_godmode_preset(arg, values)
    if action == "--apply-preset" and arg:
        return apply_godmode_preset(arg)
    if action == "--delete-preset" and arg:
        return delete_godmode_preset(arg)
    if action == "--list-presets":
        return list_godmode_presets()
    if action == "--set-battery-mode" and arg:
        return set_battery_mode(arg)
    if action == "--set-overnight" and arg:
        return set_overnight(_flag(arg))
    if action == "--set-overnight-window" and arg and arg2:
        return set_overnight_window(arg, arg2)
    if action == "--set-usb-charging" and arg:
        # compat bool; prefer --set-usb-mode off|sleep|always
        if str(arg).lower() in ("off", "sleep", "always", "onwhensleeping", "onalways", "0", "1", "2"):
            return set_usb_mode(arg)
        return set_usb_charging(_flag(arg))
    if action == "--set-usb-mode" and arg:
        return set_usb_mode(arg)
    if action == "--set-flip-to-start" and arg:
        return set_flip_to_start(_flag(arg))
    if action == "--set-instant-boot" and arg:
        return set_instant_boot(arg)
    if action == "--set-fn-lock" and arg:
        return set_fn_lock(_flag(arg))
    if action == "--set-backlight" and arg:
        return set_backlight(_int(arg, "backlight level"))
    if action == "--set-touchpad" and arg:
        return set_touchpad(_flag(arg))
    if action == "--set-mic-mute" and arg:
        return set_mic_mute(_flag(arg))
    if action == "--set-speaker-mute" and arg:
        return set_speaker_mute(_flag(arg))
    if action == "--set-volume" and arg:
        return set_speaker_volume(_int(arg, "volume"))
    if action == "--set-brightness" and arg:
        return set_brightness(_int(arg, "brightness"))
    if action == "--set-overdrive" and arg:
        return set_overdrive(_flag(arg))
    if action == "--set-logo-light" and arg:
        return set_logo_light(_flag(arg))
    if action == "--set-ports-light" and arg:
        return set_ports_light(_flag(arg))
    if action == "--set-white-backlight" and arg:
        return set_white_backlight(_int(arg, "backlight level"))
    if action == "--set-gpu-mode" and arg:
        return set_gpu_mode(arg)
    if action == "--deactivate-dgpu":
        force = arg and arg.lower() in ("1", "true", "force", "kill", "yes")
        return deactivate_dgpu(kill_processes=force)
    if action == "--restart-dgpu":
        return restart_dgpu()
    if action == "--set-gpu-oc" and arg:
        return set_gpu_oc(_flag(arg))
    if action == "--set-gpu-oc-delta" and arg and arg2:
        return set_gpu_oc_delta(_int(arg, "core delta"), _int(arg2, "mem delta"))
    if action == "--set-fan-mode" and arg:
        idx = _int(arg2, "fan index") if arg2 and str(arg2).lstrip("-").isdigit() else None
        return set_fan_mode(arg.lower() in ("auto", "1", "true"), fan_index=idx)
    if action == "--set-fan-speed" and arg:
        idx = _int(arg2, "fan index") if arg2 and str(arg2).lstrip("-").isdigit() else None
        return set_fan_speed(_int(arg, "fan percent"), fan_index=idx)
    if action == "--set-fan-fullspeed" and arg:
        return set_fan_fullspeed(_flag(arg))
    if action == "--set-fan-point" and arg and arg2:
        # --set-fan-point <fan> <point> [pwm] [temp]; pwm/temp as k=v or positional
        pwm = temp = None
        for extra in (arg3, *argv[4:]):
            if not extra or "=" not in extra:
                continue
            k, v = extra.split("=", 1)
            if k == "pwm":
                pwm = _int(v, "pwm")
            elif k == "temp":
                temp = _int(v, "temp")
        # also allow positional: --set-fan-point fan point pwm temp
        rest = [a for a in argv[3:] if "=" not in (a or "")]
        if pwm is None and len(rest) >= 1 and rest[0].lstrip("-").isdigit():
            pwm = _int(rest[0], "pwm")
        if temp is None and len(rest) >= 2 and rest[1].lstrip("-").isdigit():
            temp = _int(rest[1], "temp")
        return set_fan_point(_int(arg, "fan"), _int(arg2, "point"), pwm=pwm, temp=temp)
    if action == "--get-fan-curve":
        return {"status": "success", "curve": get_fan_curve()}
    return {"status": "error", "message": f"Unknown action: {action}"}


def main() -> None:
    if len(sys.argv) > 1:
        print(json.dumps(dispatch(sys.argv[1:])))
        return
    print(json.dumps(collect_all(), indent=2))


if __name__ == "__main__":
    main()
