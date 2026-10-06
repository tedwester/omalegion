"""Battery mode, overnight hold, always-on USB, boot options.

LLT battery modes map to /sys/class/power_supply/BAT*/charge_types:
  Rapid Charge -> Fast
  Normal       -> Standard
  Conservation -> Long_Life

LLT AlwaysOnUSB is 3-state (Off / OnWhenSleeping / OnAlways) via EnergyDrv.
On Linux we probe firmware-attributes first, then ideapad_acpi usb_charging
(bool, maps to Off / OnWhenSleeping).

LLT BatteryNightCharge is firmware. Linux has no such IOCTL, so overnight is
a software hold (Long_Life at night, restore in morning) applied explicitly
via apply_overnight_policy() — never as a side effect of a read.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import state as plugin_state
from .sysfs import first_existing, read_text, safe_write

IDEAPAD = Path("/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00")
DEFAULT_NIGHT_START, DEFAULT_NIGHT_END = 22, 7

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


def _night_window() -> tuple[int, int]:
    st = plugin_state.load()
    try:
        start = int(st.get("overnight_start", DEFAULT_NIGHT_START))
        end = int(st.get("overnight_end", DEFAULT_NIGHT_END))
    except (ValueError, TypeError):
        start, end = DEFAULT_NIGHT_START, DEFAULT_NIGHT_END
    return max(0, min(23, start)), max(0, min(23, end))


def _is_night(hour: int | None = None, start: int | None = None, end: int | None = None) -> bool:
    if start is None or end is None:
        start, end = _night_window()
    hour = time.localtime().tm_hour if hour is None else hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


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


def _current_charge_sysfs() -> str | None:
    path = _charge_types_path()
    current, _ = _parse_charge_types(read_text(path) if path else None)
    if current is None and IDEAPAD.exists():
        current = "Long_Life" if read_text(IDEAPAD / "conservation_mode") == "1" else "Standard"
    return current


def apply_overnight_policy(current_sysfs: str | None) -> str | None:
    """Hold Long_Life at night when overnight is on and mode is Normal."""
    st = plugin_state.load()
    if not st.get("overnight"):
        if st.get("overnight_hold_applied") and current_sysfs == "Long_Life":
            _write_charge_type("Standard")
            # Re-read: never clobber a value another writer set in between.
            if _current_charge_sysfs() != "Long_Life":
                st["overnight_hold_applied"] = False
                plugin_state.save(st)
                return "Standard"
            st["overnight_hold_applied"] = False
            plugin_state.save(st)
            return None
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


def _usb_nodes() -> dict:
    """Probe USB-charging interfaces. LLT has Off/OnWhenSleeping/OnAlways."""
    # 1. firmware-attributes (lenovo-wmi-other): values vary by BIOS, so the
    # advertised modes come from possible_values — never assumed.
    fw = Path("/sys/class/firmware-attributes")
    if fw.exists():
        try:
            for vendor in sorted(fw.iterdir()):
                attrs = vendor / "attributes"
                if not attrs.exists():
                    continue
                for cand in ("AlwaysOnUSB", "always_on_usb", "USBCharging", "usb_charging"):
                    node = attrs / cand
                    cur = node / "current_value"
                    if cur.exists():
                        raw = (read_text(cur) or "").strip()
                        poss = (read_text(node / "possible_values") or "")
                        mode, supports_always = _parse_usb_fw_value(raw, poss)
                        return {
                            "kind": "firmware-attributes",
                            "path": str(cur),
                            "possible": poss,
                            "mode": mode,
                            "raw": raw,
                            "supports_always": supports_always,
                        }
        except OSError:
            pass
    # 2. ideapad_acpi bool -> Off / OnWhenSleeping only.
    if IDEAPAD.exists() and (IDEAPAD / "usb_charging").exists():
        raw = read_text(IDEAPAD / "usb_charging")
        return {
            "kind": "ideapad",
            "path": str(IDEAPAD / "usb_charging"),
            "possible": "0;1",
            "mode": "sleep" if raw == "1" else "off",
            "raw": raw,
            "supports_always": False,
        }
    return {"kind": "none", "mode": None, "supports_always": False}


def _parse_usb_fw_value(raw: str, possible: str) -> tuple[str | None, bool]:
    """Map a firmware-attributes value to off/sleep/always using possible_values."""
    low = (raw or "").strip().lower()
    opts = [o.strip().lower() for o in (possible or "").replace(";", ",").split(",") if o.strip()]

    def is_always_token(t: str) -> bool:
        return "always" in t or t in ("2", "onalways", "on_always", "alwayson", "always_on")

    def is_off_token(t: str) -> bool:
        return t in ("off", "0", "disable", "disabled", "false")

    supports_always = any(is_always_token(o) for o in opts)
    if is_off_token(low):
        return "off", supports_always
    if is_always_token(low):
        return "always", supports_always
    if low in ("on", "1", "enable", "enabled", "true") or low:
        # A bare On/Enable with no always-token means sleeping-only.
        return "sleep", supports_always
    return None, supports_always


def _usb_write_candidates(target: str, possible: str) -> list[str]:
    """Candidate strings for a target mode, filtered to possible_values first."""
    opts_raw = [o.strip() for o in (possible or "").replace(";", ",").split(",") if o.strip()]
    opts = [o.lower() for o in opts_raw]
    if target == "off":
        prefs = ["Off", "Disable", "Disabled", "0"]
    elif target == "always":
        prefs = [o for o in opts_raw if "always" in o.lower()] + ["AlwaysOn", "2", "On"]
    else:
        prefs = [o for o in opts_raw if "always" not in o.lower() and o.lower() not in ("off", "disable", "disabled", "0")]
        prefs += ["On", "Enable", "1"]
    ordered = [p for p in prefs if p.lower() in opts] + [p for p in prefs if p.lower() not in opts]
    seen: list[str] = []
    for p in ordered:
        if p not in seen:
            seen.append(p)
    return seen


USB_MODES = {
    "off": {"id": "off", "label": "Off", "desc": "USB ports power off with the laptop."},
    "sleep": {"id": "sleep", "label": "On when sleeping", "desc": "Charge accessories while asleep. LLT OnWhenSleeping."},
    "always": {"id": "always", "label": "On always", "desc": "Charge even when shut down. LLT OnAlways. Needs AC on some models."},
}


def get_battery() -> dict:
    """Read-only. Never writes — overnight holds are applied by tick()."""
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
        "overnight_start": 22,
        "overnight_end": 7,
        "overnight_firmware": False,
        "overnight_note": "Software hold while running. LLT firmware Night Charge persists without OS.",
        "usb_charging": None,
        "usb_mode": None,
        "usb_modes": [],
        "usb_supports_always": False,
        "capacity_wh": None,
        "full_wh": None,
        "design_wh": None,
        "health_percent": None,
        "cycle_count": None,
        "voltage_now": None,
        "power_now_w": None,
        "current_a": None,
        "temp_c": None,
        "model": None,
        "manufacturer": None,
        "technology": None,
    }

    bat_dir = _bat_dir()
    if bat_dir:
        bat["present"] = True
        bat["status"] = read_text(bat_dir / "status") or "Unknown"
        cap = read_text(bat_dir / "capacity")
        energy_now = read_text(bat_dir / "energy_now")
        energy_full = read_text(bat_dir / "energy_full")
        energy_design = read_text(bat_dir / "energy_full_design") or read_text(bat_dir / "energy_design")
        charge_now = read_text(bat_dir / "charge_now")
        charge_full = read_text(bat_dir / "charge_full")

        if energy_now and energy_full and energy_full != "0":
            try:
                bat["capacity_wh"] = round(int(energy_now) / 1_000_000, 2)
                bat["full_wh"] = round(int(energy_full) / 1_000_000, 2)
                bat["percent"] = int(round((int(energy_now) / int(energy_full)) * 100))
                if energy_design:
                    bat["design_wh"] = round(int(energy_design) / 1_000_000, 2)
                    bat["health_percent"] = round((int(energy_full) / int(energy_design)) * 100, 1)
            except ValueError:
                pass
        elif charge_now and charge_full and charge_full != "0":
            try:
                bat["percent"] = int(round((int(charge_now) / int(charge_full)) * 100))
                bat["full_wh"] = round(int(charge_full) / 1_000_000, 2)
            except ValueError:
                pass
        if bat["percent"] is None and cap and cap.strip().lstrip("-").isdigit():
            bat["percent"] = max(0, min(100, int(cap.strip())))

        cycles = read_text(bat_dir / "cycle_count")
        bat["cycle_count"] = int(cycles) if cycles and cycles.isdigit() else None
        bat["model"] = read_text(bat_dir / "model_name")
        bat["manufacturer"] = read_text(bat_dir / "manufacturer")
        bat["technology"] = read_text(bat_dir / "technology")
        voltage = read_text(bat_dir / "voltage_now")
        bat["voltage_now"] = round(int(voltage) / 1_000_000, 3) if voltage and voltage.isdigit() else None
        power = read_text(bat_dir / "power_now")
        current = read_text(bat_dir / "current_now")
        if power and power.lstrip("-").isdigit():
            bat["power_now_w"] = round(int(power) / 1_000_000, 2)
        elif current and voltage and current.lstrip("-").isdigit() and voltage.isdigit():
            bat["power_now_w"] = round(abs(int(current)) * int(voltage) / 1_000_000_000_000, 2)
            bat["current_a"] = round(int(current) / 1_000_000, 3)
        temp = read_text(bat_dir / "temp")
        if temp and temp.lstrip("-").isdigit():
            # power_supply temp is tenths of °C
            bat["temp_c"] = round(int(temp) / 10, 1)

    for ac in Path("/sys/class/power_supply").glob("AC*"):
        bat["ac_connected"] = read_text(ac / "online") == "1"
        break
    for adp in Path("/sys/class/power_supply").glob("ADP*"):
        if read_text(adp / "online") == "1":
            bat["ac_connected"] = True

    raw_types = read_text(_charge_types_path()) if _charge_types_path() else None
    current_sysfs, choices = _parse_charge_types(raw_types)

    has_charge_iface = _charge_types_path() is not None
    if current_sysfs is None and IDEAPAD.exists():
        current_sysfs = "Long_Life" if read_text(IDEAPAD / "conservation_mode") == "1" else "Standard"
        choices = ["Standard", "Long_Life"]
        has_charge_iface = (IDEAPAD / "conservation_mode").exists()
        if not raw_types:
            raw_types = "ideapad conservation_mode"

    mode_id = SYSFS_TO_MODE.get(current_sysfs or "", "normal")
    st = plugin_state.load()
    start, end = _night_window()
    bat["mode"] = mode_id
    bat["mode_label"] = BATTERY_MODES[mode_id]["label"]
    bat["has_charge_iface"] = has_charge_iface
    bat["overnight"] = bool(st.get("overnight"))
    bat["overnight_active"] = bool(st.get("overnight") and _is_night(start=start, end=end))
    bat["overnight_start"] = start
    bat["overnight_end"] = end
    if not has_charge_iface:
        # No charge-type interface at all: report modes but mark them
        # unavailable instead of failing at write time (LLT hides).
        bat["available_modes"] = [
            {**info, "selected": info["id"] == mode_id, "available": False}
            for info in BATTERY_MODES.values()
        ]
    else:
        bat["available_modes"] = [
            {**info, "selected": info["id"] == mode_id, "available": info["sysfs"] in choices or not choices}
            for info in BATTERY_MODES.values()
            if not choices or info["sysfs"] in choices
        ]

    usb = _usb_nodes()
    bat["usb_supports_always"] = bool(usb.get("supports_always"))
    if usb.get("mode") is not None:
        bat["usb_mode"] = usb["mode"]
        bat["usb_charging"] = usb["mode"] != "off"
        avail = ["off", "sleep"] + (["always"] if usb.get("supports_always") else [])
        bat["usb_modes"] = [
            {**USB_MODES[mid], "selected": mid == usb["mode"], "available": True}
            for mid in avail
        ]
    else:
        bat["usb_modes"] = []

    return bat


def tick_battery() -> dict:
    """Maintenance writes, called by engine poll — never by reads.

    1. Overnight hold/release.
    2. Restore persisted battery mode (LLT EnsureCorrectBatteryModeIsSet
       equivalent): only when overnight is off, no hold is active, and the
       firmware value differs from the last explicitly set mode.
    """
    current = _current_charge_sysfs()
    applied = apply_overnight_policy(current)
    if applied:
        current = applied
    restored = None
    st = plugin_state.load()
    saved = st.get("battery_mode")
    if (
        saved in BATTERY_MODES
        and not st.get("overnight")
        and not st.get("overnight_hold_applied")
        and current is not None
        and SYSFS_TO_MODE.get(current, "normal") != saved
    ):
        res = _write_charge_type(BATTERY_MODES[saved]["sysfs"])
        if res.get("status") == "success" and _current_charge_sysfs() == BATTERY_MODES[saved]["sysfs"]:
            restored = saved
    return {"applied": applied, "restored": restored}


def set_battery_mode(mode: str) -> dict:
    info = BATTERY_MODES.get(mode)
    if not info:
        return {"status": "error", "message": f"Unknown battery mode: {mode}"}
    result = _write_charge_type(info["sysfs"])
    if result["status"] == "success":
        st = plugin_state.load()
        st["overnight_hold_applied"] = False
        st["battery_mode"] = mode
        plugin_state.save(st)
        result["battery_mode"] = info["label"]
    return result


def set_overnight(enabled: bool) -> dict:
    st = plugin_state.load()
    st["overnight"] = bool(enabled)
    plugin_state.save(st)
    # Route through the policy with a fresh read: disabling restores Standard
    # only if the hold value is still in place (no blind clobber).
    apply_overnight_policy(_current_charge_sysfs())
    if not enabled:
        st = plugin_state.load()
        st["overnight_hold_applied"] = False
        plugin_state.save(st)
    return {"status": "success", "overnight": bool(enabled)}


def set_overnight_window(start: int, end: int) -> dict:
    try:
        s, e = int(start), int(end)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid overnight window"}
    if not (0 <= s <= 23 and 0 <= e <= 23):
        return {"status": "error", "message": "Hours must be 0–23"}
    st = plugin_state.load()
    st["overnight_start"] = s
    st["overnight_end"] = e
    plugin_state.save(st)
    return {"status": "success", "overnight_start": s, "overnight_end": e}


def set_usb_charging(enabled: bool) -> dict:
    # Back-compat bool: True -> sleep, False -> off (LLT 3-state default).
    return set_usb_mode("sleep" if enabled else "off")


def set_usb_mode(mode: str) -> dict:
    mode = str(mode).strip().lower()
    aliases = {"off": "off", "0": "off", "sleep": "sleep", "1": "sleep",
               "on": "sleep", "onwhensleeping": "sleep", "when-sleeping": "sleep",
               "always": "always", "2": "always", "onalways": "always"}
    target = aliases.get(mode)
    if target is None:
        return {"status": "error", "message": f"Unknown USB mode: {mode}"}
    usb = _usb_nodes()
    if usb.get("kind") == "none":
        return {"status": "error", "message": "Always-on USB is not exposed (ideapad_acpi / firmware-attributes missing)"}
    if target == "always" and not usb.get("supports_always"):
        return {"status": "error", "message": "On-always is not exposed on this firmware (only Off / On-when-sleeping)."}
    if usb.get("kind") == "firmware-attributes":
        path = Path(str(usb["path"]))
        # Candidates ordered by possible_values first (BIOS truth), then guesses.
        last: dict = {"status": "error", "message": "Failed to set USB mode"}
        for cand in _usb_write_candidates(target, str(usb.get("possible") or "")):
            last = safe_write(path, cand)
            if last.get("status") == "success":
                last["usb_mode"] = target
                st = plugin_state.load()
                st["usb_mode"] = target
                plugin_state.save(st)
                return last
        return last
    result = safe_write(Path(str(usb["path"])), "1" if target != "off" else "0")
    if result["status"] == "success":
        result["usb_mode"] = target if target != "always" else "sleep"
        result["usb_charging"] = target != "off"
        st = plugin_state.load()
        st["usb_mode"] = result["usb_mode"]
        plugin_state.save(st)
    return result


def _read_efivar(pattern: str) -> str | None:
    efivars = Path("/sys/firmware/efi/efivars")
    if not efivars.exists():
        return None
    try:
        for entry in efivars.iterdir():
            if entry.name.lower().startswith(pattern.lower()):
                data = entry.read_bytes()[4:]  # skip attributes u32
                return data.hex()
    except OSError:
        return None
    return None


def get_boot_options() -> dict:
    """InstantBoot / FlipToStart / BootLogo — LLT features, efivar-gated."""
    flip_hex = _read_efivar("FBSWIF-")
    flip_supported = flip_hex is not None
    flip_on = flip_hex is not None and flip_hex[:2] not in ("00", "")
    bootlogo = _read_efivar("LBLDESP-") is not None or _read_efivar("LBLDVC-") is not None
    # InstantBoot has no Linux efivar; WMI-only on LLT. Report unsupported
    # honestly instead of faking a toggle.
    return {
        "flip_to_start": {"supported": flip_supported, "enabled": bool(flip_on)},
        "instant_boot": {
            "supported": False,
            "reason": "Firmware WMI only (LLT InstantBootAc/UsbPD). No Linux sysfs/efivar exposes it.",
        },
        "boot_logo": {
            "supported": bootlogo,
            "reason": None if bootlogo else "LBLDESP/LBLDVC efivars not present.",
        },
    }


def set_flip_to_start(enabled: bool) -> dict:
    efivars = Path("/sys/firmware/efi/efivars")
    target = None
    if efivars.exists():
        try:
            for entry in efivars.iterdir():
                if entry.name.lower().startswith("fbswif-"):
                    target = entry
                    break
        except OSError:
            pass
    if target is None:
        return {"status": "error", "message": "Flip To Start efivar (FBSWIF) not present on this device"}
    try:
        raw = target.read_bytes()
        attrs = raw[:4]
        payload = bytearray(raw[4:])
        if len(payload) < 1:
            return {"status": "error", "message": "Unexpected FBSWIF size"}
        payload[0] = 1 if enabled else 0
        # efivarfs requires immutable bit cleared; use pkexec chattr+dd via shell
        import subprocess

        tmp = Path("/tmp/omalegion_fbswif.bin")
        tmp.write_bytes(attrs + bytes(payload))
        r1 = subprocess.run(["pkexec", "chattr", "-i", str(target)], capture_output=True, timeout=10)
        if r1.returncode != 0:
            return {"status": "error", "message": "Need root to clear efivar immutable bit"}
        r2 = subprocess.run(
            ["pkexec", "dd", f"if={tmp}", f"of={target}", "bs=4096", "conv=notrunc"],
            capture_output=True, timeout=10,
        )
        subprocess.run(["pkexec", "chattr", "+i", str(target)], capture_output=True, timeout=10)
        if r2.returncode == 0:
            return {"status": "success", "flip_to_start": bool(enabled)}
        return {"status": "error", "message": "Failed to write FBSWIF efivar"}
    except OSError as exc:
        return {"status": "error", "message": f"Failed to write FBSWIF: {exc}"}


def set_instant_boot(_mode: str) -> dict:
    return {
        "status": "error",
        "message": "Instant Boot is firmware WMI only (LLT InstantBootAc/UsbPD). Switch it in BIOS.",
    }
