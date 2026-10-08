"""Fn-lock and keyboard backlight. Camera power is intentionally omitted."""

from __future__ import annotations

from pathlib import Path

from .sysfs import read_text, safe_write

IDEAPAD = Path("/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00")


def get_input() -> dict:
    info = {
        "fn_lock": False,
        "backlight_available": False,
        "backlight_brightness": None,
        "backlight_max": None,
    }
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
