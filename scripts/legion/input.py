"""Fn-lock, keyboard backlight, and touchpad control."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .sysfs import read_text, run_cmd, safe_write

IDEAPAD = Path("/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00")
TOUCHPAD_DISABLED_NAME = Path.home() / ".local/state/omarchy/toggles/hypr/touchpad-disabled-name"


def _touchpad_device_name() -> str | None:
    name = run_cmd(["omarchy-hw-touchpad"], timeout=2.0)
    if name:
        return name.strip()
    return None


def _touchpad_enabled() -> bool | None:
    if not _touchpad_device_name():
        return None
    return not TOUCHPAD_DISABLED_NAME.is_file()


def get_touchpad() -> dict:
    device = _touchpad_device_name()
    info = {
        "available": bool(device),
        "enabled": None,
        "backend": "omarchy" if device else None,
    }
    if device:
        info["enabled"] = not TOUCHPAD_DISABLED_NAME.is_file()
        info["device_name"] = device
    return info


def set_touchpad(enabled: bool) -> dict:
    if not _touchpad_device_name():
        return {"status": "error", "message": "No touchpad device found"}

    action = "on" if enabled else "off"
    try:
        result = subprocess.run(
            ["omarchy-toggle-touchpad", action],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "message": f"Failed to toggle touchpad: {exc}"}

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        return {"status": "error", "message": message or "Touchpad toggle failed"}

    return {"status": "success", "backend": "omarchy", "touchpad": bool(enabled)}


def get_input() -> dict:
    info = {
        "fn_lock": False,
        "backlight_available": False,
        "backlight_brightness": None,
        "backlight_max": None,
    }
    info.update(get_touchpad())

    if IDEAPAD.exists():
        info["fn_lock"] = read_text(IDEAPAD / "fn_lock") == "1"

    for led in Path("/sys/class/leds").glob("*"):
        name = led.name.lower()
        if "kbd" in name or "keyboard" in name:
            info["backlight_available"] = True
            br = read_text(led / "brightness")
            mx = read_text(led / "max_brightness")
            info["backlight_brightness"] = int(br) if br and br.isdigit() else None
            info["backlight_max"] = int(mx) if mx and mx.isdigit() else None
            info["backlight_path"] = str(led)
            break
    return info


def set_fn_lock(enabled: bool) -> dict:
    if not IDEAPAD.exists():
        return {"status": "error", "message": "ideapad_acpi not found"}
    result = safe_write(IDEAPAD / "fn_lock", "1" if enabled else "0")
    if result["status"] == "success":
        result["fn_lock"] = bool(enabled)
    return result


def set_backlight(level: int) -> dict:
    info = get_input()
    path = info.get("backlight_path")
    if not path:
        return {"status": "error", "message": "Keyboard backlight is not available"}
    mx = info.get("backlight_max") or 2
    value = max(0, min(mx, int(level)))
    result = safe_write(Path(path) / "brightness", str(value))
    if result["status"] == "success":
        result["backlight"] = value
    return result
