"""Keyboard / logo / ports lighting.

LLT stacks: White 3-level, One-level, RGB 4-zone presets, Spectrum per-key
0-6 profiles + Aurora, LampArray/Dynamic Lighting, PanelLogo, PortsBacklight.
Linux reality:
  White levels -> leds kbd_backlight (supported)
  Y-Logo / IO-port light -> legion-laptop sysfs (supported where exposed)
  RGB 4-zone / Spectrum per-key / LampArray -> HID proprietary, needs
    openrgb / vendor driver; reported unsupported with reason (like LLT hides
    when controllers unsupported), never faked.
"""

from __future__ import annotations

from pathlib import Path

from .input import _kbd_led
from .sysfs import read_text, safe_write


def _legion_base() -> Path | None:
    try:
        for base in Path("/sys/module/legion_laptop/drivers").glob("*/PNP0C09:00"):
            if base.exists():
                return base
    except OSError:
        pass
    return None


def _find_hid_lighting() -> dict:
    found = {"rgb_hid": False, "spectrum_hid": False, "nodes": []}
    try:
        for dev in Path("/sys/bus/hid/devices").glob("*"):
            uevent = read_text(dev / "uevent") or ""
            name = (read_text(dev / "name") or "").lower()
            blob = (uevent + " " + name).lower()
            if "048d" in blob or "lenovo" in blob:
                found["nodes"].append(dev.name)
                if "rgb" in blob or "c135" in blob or "c137" in blob:
                    found["rgb_hid"] = True
                if "spectrum" in blob or "c139" in blob or "c13a" in blob:
                    found["spectrum_hid"] = True
    except OSError:
        pass
    return found


def get_lighting() -> dict:
    led = _kbd_led()
    white = None
    if led is not None:
        br = read_text(led / "brightness")
        mx = read_text(led / "max_brightness")
        try:
            white = {"brightness": int(br) if br else None,
                     "max": int(mx) if mx else 2, "path": str(led)}
        except ValueError:
            white = {"brightness": None, "max": 2, "path": str(led)}
    base = _legion_base()
    ylogo = read_text(base / "ylogo_light") if base and (base / "ylogo_light").exists() else None
    ioport = read_text(base / "ioport_light") if base and (base / "ioport_light").exists() else None
    hid = _find_hid_lighting()
    return {
        "white": white,
        "white_available": white is not None,
        "ylogo": {"supported": ylogo is not None, "enabled": ylogo == "1", "raw": ylogo},
        "ports": {"supported": ioport is not None, "enabled": ioport == "1", "raw": ioport},
        "rgb": {"supported": False,
                "reason": "RGB 4-zone needs Lenovo HID + Vantage ownership (LLT RGBKeyboardBacklightController). No stable Linux driver — use OpenRGB if your model is supported." if not hid["rgb_hid"] else "HID node found but no stable Linux setter; use OpenRGB."},
        "spectrum": {"supported": False,
                     "reason": "Spectrum per-key needs HID feature reports + Aurora capture (LLT SpectrumKeyboardBacklightController). Unsupported on Linux."},
        "lamp_array": {"supported": False, "reason": "Dynamic Lighting / LampArray is Windows-only."},
        "hid_nodes": hid["nodes"][:6],
    }


def set_white_backlight(level: int) -> dict:
    from .input import set_backlight

    return set_backlight(level)


def set_logo_light(enabled: bool) -> dict:
    base = _legion_base()
    if not base or not (base / "ylogo_light").exists():
        return {"status": "error", "message": "Panel/Y-logo light not exposed (legion-laptop missing)"}
    r = safe_write(base / "ylogo_light", "1" if enabled else "0")
    if r.get("status") == "success":
        r["logo"] = bool(enabled)
    return r


def set_ports_light(enabled: bool) -> dict:
    base = _legion_base()
    if not base or not (base / "ioport_light").exists():
        return {"status": "error", "message": "Ports backlight not exposed (legion-laptop missing)"}
    r = safe_write(base / "ioport_light", "1" if enabled else "0")
    if r.get("status") == "success":
        r["ports"] = bool(enabled)
    return r
