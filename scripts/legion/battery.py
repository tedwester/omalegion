from __future__ import annotations

import time
from pathlib import Path

from . import state as plugin_state
from .sysfs import first_existing, ideapad_dir, read_text, safe_write

IDEAPAD = ideapad_dir()
NIGHT_START, NIGHT_END = 22, 7

BATTERY_MODES = {
    "rapid": {
        "id": "rapid",
        "sysfs": "Fast",
        "label": "Rapid Charge",
        "desc": "Charges as fast as the adapter allows.",
    },
    "normal": {
        "id": "normal",
        "sysfs": "Standard",
        "label": "Normal",
        "desc": "Standard charge to 100%. Everyday use.",
    },
    "conservation": {
        "id": "conservation",
        "sysfs": "Long_Life",
        "label": "Conservation",
        "desc": "Caps charge around 80% to extend battery lifespan.",
    },
}

SYSFS_TO_MODE = {v["sysfs"]: k for k, v in BATTERY_MODES.items()}


def _bat_dir() -> Path | None:
    return first_existing(*sorted(Path("/sys/class/power_supply").glob("BAT*")))


def _charge_types_path() -> Path | None:
    bat = _bat_dir()
    if bat and (bat / "charge_types").exists():
        return bat / "charge_types"
    return None


def _parse_charge_types(raw: str | None) -> tuple[str | None, list[str]]:
    if not raw:
        return None, []
    current = None
    choices = []
    for token in raw.replace("[", " [").replace("]", "] ").split():
        if token.startswith("[") and token.endswith("]"):
            name = token[1:-1]
            current = name
            choices.append(name)
        else:
            choices.append(token)
    return current, choices


def _is_night(hour: int | None = None) -> bool:
    hour = time.localtime().tm_hour if hour is None else hour
    return hour >= NIGHT_START or hour < NIGHT_END


def _write_charge_type(sysfs_name: str) -> dict:
    path = _charge_types_path()
    if path:
        result = safe_write(path, sysfs_name)
        if result["status"] == "success":
            return result

    if IDEAPAD.exists() and sysfs_name in ("Standard", "Long_Life"):
        result = safe_write(IDEAPAD / "conservation_mode", "1" if sysfs_name == "Long_Life" else "0")
        if result["status"] == "success":
            return result

    return {"status": "error", "message": "No battery charge-type interface found"}


def apply_overnight_policy(current_sysfs: str | None) -> str | None:
    st = plugin_state.load()
    if not st.get("overnight"):
        if st.get("overnight_hold_applied") and current_sysfs == "Long_Life":
            _write_charge_type("Standard")
            st["overnight_hold_applied"] = False
            plugin_state.save(st)
            return "Standard"
        return None

    if current_sysfs == "Fast":
        return None

    if _is_night():
        if current_sysfs != "Long_Life":
            _write_charge_type("Long_Life")
            st["overnight_hold_applied"] = True
            plugin_state.save(st)
            return "Long_Life"
        return None

    if st.get("overnight_hold_applied") and current_sysfs == "Long_Life":
        _write_charge_type("Standard")
        st["overnight_hold_applied"] = False
        plugin_state.save(st)
        return "Standard"
    return None


def get_battery() -> dict:
    bat = {
        "present": False,
        "status": "Unknown",
        "percent": None,
        "ac_connected": False,
        "mode": "normal",
        "mode_label": "Normal",
        "available_modes": [],
        "overnight": False,
        "overnight_active": False,
        "usb_charging": None,
        "capacity_wh": None,
        "full_wh": None,
        "design_wh": None,
        "health_percent": None,
        "cycle_count": None,
        "voltage_now": None,
        "power_now_w": None,
        "model": None,
        "manufacturer": None,
    }

    bat_dir = _bat_dir()
    if bat_dir:
        bat["present"] = True
        bat["status"] = read_text(bat_dir / "status") or "Unknown"
        cap = read_text(bat_dir / "capacity")
        energy_now = read_text(bat_dir / "energy_now")
        energy_full = read_text(bat_dir / "energy_full")
        energy_design = read_text(bat_dir / "energy_full_design") or read_text(bat_dir / "energy_design")

        if energy_now and energy_full and energy_full != "0":
            try:
                now_i, full_i = int(energy_now), int(energy_full)
                bat["capacity_wh"] = round(now_i / 1_000_000, 2)
                bat["full_wh"] = round(full_i / 1_000_000, 2)
                bat["percent"] = round((now_i / full_i) * 100, 1)
                if energy_design:
                    design_i = int(energy_design)
                    bat["design_wh"] = round(design_i / 1_000_000, 2)
                    bat["health_percent"] = round((full_i / design_i) * 100, 1)
            except (ValueError, ZeroDivisionError):
                pass
        if bat["percent"] is None and cap and cap.isdigit():
            bat["percent"] = int(cap)

        cycles = read_text(bat_dir / "cycle_count")
        bat["cycle_count"] = int(cycles) if cycles and cycles.isdigit() else None
        bat["model"] = read_text(bat_dir / "model_name")
        bat["manufacturer"] = read_text(bat_dir / "manufacturer")
        voltage = read_text(bat_dir / "voltage_now")
        bat["voltage_now"] = round(int(voltage) / 1_000_000, 3) if voltage and voltage.isdigit() else None
        power = read_text(bat_dir / "power_now")
        bat["power_now_w"] = round(int(power) / 1_000_000, 2) if power and power.isdigit() else None

    for ac in Path("/sys/class/power_supply").glob("AC*"):
        bat["ac_connected"] = read_text(ac / "online") == "1"
        break

    raw_types = read_text(_charge_types_path()) if _charge_types_path() else None
    current_sysfs, choices = _parse_charge_types(raw_types)

    if current_sysfs is None and IDEAPAD.exists():
        current_sysfs = "Long_Life" if read_text(IDEAPAD / "conservation_mode") == "1" else "Standard"
        choices = ["Standard", "Long_Life"]
        if not raw_types:
            raw_types = "ideapad conservation_mode"

    # NOTE: reads must not write. The overnight hold is applied only by the
    # explicit set_overnight()/set_battery_mode() actions below, never during
    # polling. Overnight therefore only takes effect while this OS runs and
    # an action (toggle or poll-triggered apply) runs at night.
    mode_id = SYSFS_TO_MODE.get(current_sysfs or "", "normal")
    st = plugin_state.load()
    bat["mode"] = mode_id
    bat["mode_label"] = BATTERY_MODES[mode_id]["label"]
    bat["overnight"] = bool(st.get("overnight"))
    bat["overnight_active"] = bool(st.get("overnight") and _is_night() and current_sysfs != "Fast")
    bat["available_modes"] = [
        {**info, "selected": info["id"] == mode_id, "available": info["sysfs"] in choices or not choices}
        for info in BATTERY_MODES.values()
        if not choices or info["sysfs"] in choices
    ]

    if IDEAPAD.exists():
        usb = read_text(IDEAPAD / "usb_charging")
        bat["usb_charging"] = usb == "1"

    return bat


def set_battery_mode(mode: str) -> dict:
    info = BATTERY_MODES.get(mode)
    if not info:
        return {"status": "error", "message": f"Unknown battery mode: {mode}"}
    result = _write_charge_type(info["sysfs"])
    if result["status"] == "success":
        st = plugin_state.load()
        st["overnight_hold_applied"] = False
        plugin_state.save(st)
        result["battery_mode"] = info["label"]
    return result


def set_overnight(enabled: bool) -> dict:
    st = plugin_state.load()
    st["overnight"] = bool(enabled)
    if not enabled:
        if st.get("overnight_hold_applied"):
            _write_charge_type("Standard")
        st["overnight_hold_applied"] = False
    plugin_state.save(st)
    path = _charge_types_path()
    current, _ = _parse_charge_types(read_text(path) if path else None)
    apply_overnight_policy(current)
    return {"status": "success", "overnight": bool(enabled)}


def set_usb_charging(enabled: bool) -> dict:
    if not IDEAPAD.exists():
        return {"status": "error", "message": "Always-on USB is not exposed (ideapad_acpi missing)"}
    result = safe_write(IDEAPAD / "usb_charging", "1" if enabled else "0")
    if result["status"] == "success":
        result["usb_charging"] = bool(enabled)
    return result
