"""Display controls.

LLT: HDR On/Off, RefreshRate (incl. dynamic/boost), Resolution, DpiScale,
DisplayBrightness 0-100, OverDrive On/Off, AutoColorManagement, TurnOffMonitors.
Linux mapping (compositor-dependent, capability-gated):
  Brightness -> sysfs backlight (internal) + ddcutil (external)
  Refresh/Resolution -> drm modes (read) + xrandr/hyprctl/wlr-randr/kscreen (write)
  HDR -> drm HDR properties where exposed; otherwise unsupported with reason
  OverDrive -> firmware WMI only; unsupported unless firmware-attribute exists
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .sysfs import read_text, run_cmd, safe_write


def _backlight_dev() -> Path | None:
    bl = Path("/sys/class/backlight")
    if not bl.exists():
        return None
    try:
        devs = sorted(bl.iterdir())
    except OSError:
        return None
    # Prefer intel/amdgpu internal over acpi_video
    for dev in devs:
        if dev.name.startswith(("intel_", "amdgpu_", "nvidia_")):
            return dev
    for dev in devs:
        if "acpi_video" not in dev.name:
            return dev
    return devs[0] if devs else None


def _drm_panels() -> list[dict]:
    panels = []
    drm = Path("/sys/class/drm")
    if not drm.exists():
        return panels
    try:
        entries = sorted(drm.glob("card*-*/modes"))
    except OSError:
        return panels
    for modes_f in entries:
        conn = modes_f.parent.name  # e.g. eDP-1
        card = modes_f.parent.parent.name
        status = read_text(modes_f.parent / "status") or "unknown"
        enabled = read_text(modes_f.parent / "enabled") or ""
        try:
            modes = (modes_f.read_text().strip().splitlines() if modes_f.exists() else [])
        except OSError:
            modes = []
        # current mode: first line is preferred; actual via `cat status`? use enabled
        panels.append({
            "connector": conn,
            "card": card,
            "status": status,
            "enabled": enabled,
            "internal": "eDP" in conn or "LVDS" in conn or "DSI" in conn,
            "modes": modes[:12],
            "current_mode": modes[0] if modes else None,
        })
    return panels


def _hdr_state() -> dict:
    # drm exposes HDR via hdmi output properties, not sysfs files on most
    # kernels. Probe for hdr_output_metadata / Colorspace props via debugfs.
    hdr_nodes = []
    try:
        for p in Path("/sys/kernel/debug/dri").rglob("*hdr*"):
            hdr_nodes.append(str(p))
    except OSError:
        pass
    return {"supported": bool(hdr_nodes), "nodes": hdr_nodes[:4]}


def get_display() -> dict:
    bl = _backlight_dev()
    brightness = None
    if bl is not None:
        cur = read_text(bl / "brightness")
        mx = read_text(bl / "max_brightness")
        try:
            if cur is not None and mx is not None:
                brightness = int(round(int(cur) / max(1, int(mx)) * 100))
        except (ValueError, ZeroDivisionError):
            pass
    panels = _drm_panels()
    hdr = _hdr_state()
    tools = {
        "xrandr": bool(shutil.which("xrandr")),
        "hyprctl": bool(shutil.which("hyprctl")),
        "wlr-randr": bool(shutil.which("wlr-randr")),
        "kscreen-doctor": bool(shutil.which("kscreen-doctor")),
        "ddcutil": bool(shutil.which("ddcutil")),
        "brightnessctl": bool(shutil.which("brightnessctl")),
    }
    # Overdrive: firmware-only unless attribute exists
    has_od_attr = False
    fw = Path("/sys/class/firmware-attributes")
    if fw.exists():
        try:
            for vendor in fw.iterdir():
                if ((vendor / "attributes" / "OverDrive").exists()
                        or (vendor / "attributes" / "overdrive").exists()):
                    has_od_attr = True
        except OSError:
            pass
    return {
        "brightness": brightness,
        "brightness_available": bl is not None or tools["brightnessctl"] or tools["ddcutil"],
        "brightness_path": str(bl) if bl else None,
        "panels": panels,
        "refresh_available": tools["xrandr"] or tools["hyprctl"] or tools["wlr-randr"] or tools["kscreen-doctor"],
        "resolution_available": tools["xrandr"] or tools["hyprctl"] or tools["wlr-randr"] or tools["kscreen-doctor"],
        "hdr": {"supported": hdr["supported"], "reason": None if hdr["supported"] else "No drm HDR nodes exposed on this kernel/compositor."},
        "overdrive": {"supported": has_od_attr,
                      "reason": None if has_od_attr else "Panel OverDrive is firmware WMI only (LLT OverDriveFeature). Switch in BIOS."},
        "tools": tools,
    }


def set_brightness(percent: int) -> dict:
    try:
        pct = max(0, min(100, int(percent)))
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid brightness (0–100)"}
    bl = _backlight_dev()
    if bl is not None:
        mx_raw = read_text(bl / "max_brightness") or "100"
        try:
            mx = max(1, int(mx_raw))
        except ValueError:
            mx = 100
        r = safe_write(bl / "brightness", str(int(round(mx * pct / 100))))
        if r.get("status") == "success":
            r["brightness"] = pct
            return r
    if shutil.which("brightnessctl"):
        out = run_cmd(["brightnessctl", "set", f"{pct}%"], timeout=3.0)
        if out is not None:
            return {"status": "success", "brightness": pct, "method": "brightnessctl"}
    return {"status": "error", "message": "Brightness control not available (no backlight sysfs / brightnessctl)"}


def set_refresh_rate(_rate: str) -> dict:
    return {"status": "error",
            "message": "Refresh-rate switching needs a compositor tool (hyprctl / wlr-randr / kscreen-doctor / xrandr). Use your display settings; detection is shown above."}


def set_hdr(_on: bool) -> dict:
    return {"status": "error",
            "message": "HDR toggle is compositor-controlled on Linux (KDE/Wayland color pipeline). No stable sysfs API — use your desktop display settings."}


def set_overdrive(_on: bool) -> dict:
    return {"status": "error",
            "message": "Panel OverDrive is firmware WMI only (LLT OverDriveFeature). Switch it in BIOS."}
