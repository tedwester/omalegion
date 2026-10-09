from __future__ import annotations

import os
import re
import time
from pathlib import Path

from . import state as plugin_state
from .sysfs import read_text, run_cmd, safe_write

PPD_BUS = "net.hadess.PowerProfiles"
PPD_PATH = "/net/hadess/PowerProfiles"
PPD_IFACE = "net.hadess.PowerProfiles"

PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
PLATFORM_CHOICES = Path("/sys/firmware/acpi/platform_profile_choices")

BATTERY_BLOCKED_PROFILES = frozenset({"performance", "max-power", "custom"})

PPD_TO_PROFILE = {
    "power-saver": "low-power",
    "balanced": "balanced",
    "performance": "performance",
}

LEGION_TO_PROFILE = {
    "quiet": "low-power",
    "balanced": "balanced",
    "performance": "performance",
    "extreme": "max-power",
    "custom": "custom",
    "low-power": "low-power",
    "max-power": "max-power",
    "power-saver": "low-power",
}


def _normalize_mode(mode: str) -> str | None:
    normalized = str(mode).strip().lower().replace("_", "-")
    aliases = {
        "quiet": "low-power",
        "low power": "low-power",
        "balanced": "balanced",
        "balance": "balanced",
        "performance": "performance",
        "extreme": "max-power",
        "max power": "max-power",
        "custom": "custom",
    }
    return LEGION_TO_PROFILE.get(normalized) or aliases.get(normalized)


PROFILE_META = {
    "low-power": {
        "id": "quiet",
        "label": "Quiet",
        "desc": "Silent fans, lower TDP, best battery. Same mode as Fn+Q quiet.",
        "ppd": "power-saver",
    },
    "balanced": {
        "id": "balanced",
        "label": "Balanced",
        "desc": "Auto clocks for everyday use. Default Legion thermal mode.",
        "ppd": "balanced",
    },
    "performance": {
        "id": "performance",
        "label": "Performance",
        "desc": "Higher power limits and fans. Syncs Omarchy to Performance.",
        "ppd": "performance",
    },
    "max-power": {
        "id": "extreme",
        "label": "Extreme",
        "desc": "Maximum Legion power envelope. Syncs Omarchy to Performance.",
        "ppd": "performance",
    },
    "custom": {
        "id": "custom",
        "label": "Custom",
        "desc": "Manual TDP limits from firmware-attributes. Not on Fn+Q.",
        "ppd": None,
    },
}

def _firmware_attr_base() -> Path | None:
    for base in sorted(Path("/sys/class/firmware-attributes").glob("*")):
        if (base / "attributes").is_dir():
            return base / "attributes"
    return None


FIRMWARE_ATTR = _firmware_attr_base() or Path("/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes")

CUSTOM_NEEDS_MODULE = (
    "Custom mode needs the legion-laptop kernel module on this firmware."
)


def legion_laptop_loaded() -> bool:
    return Path("/sys/module/legion_laptop").exists()


def _legion_profile_node() -> Path | None:
    for choices in sorted(Path("/sys/devices/platform/legion/platform-profile").glob("*/choices")):
        node = choices.parent
        if read_text(node / "name") == "lenovo-legion" and (node / "profile").exists():
            return node / "profile"
    return None


def _choices() -> list[str]:
    node = _legion_profile_node()
    if node is not None:
        raw = read_text(node.parent / "choices")
        if raw:
            return raw.split()
    raw = read_text(PLATFORM_CHOICES)
    if raw:
        return raw.split()
    return ["low-power", "balanced", "performance"]


def _write_profile(profile: str) -> dict:
    node = _legion_profile_node()
    if node is not None:
        result = safe_write(node, profile)
        if result["status"] == "success":
            return result
    return safe_write(PLATFORM_PROFILE, profile)


def _ac_connected() -> bool:
    for ac in Path("/sys/class/power_supply").glob("AC*"):
        if read_text(ac / "online") == "1":
            return True
    return False


def _get_ppd() -> str | None:
    out = run_cmd(
        ["busctl", "--system", "get-property", PPD_BUS, PPD_PATH, PPD_IFACE, "ActiveProfile"],
        timeout=2.0,
    )
    if not out:
        return None
    match = re.search(r'"([^"]+)"', out)
    return match.group(1) if match else None


def _ppd_profiles() -> list[str]:
    out = run_cmd(
        ["busctl", "--system", "get-property", PPD_BUS, PPD_PATH, PPD_IFACE, "Profiles"],
        timeout=2.0,
    )
    if not out:
        return []
    return re.findall(r'"Profile" s "([^"]+)"', out)


def _ppd_set(profile: str) -> bool:
    run_cmd(
        ["busctl", "--system", "set-property", PPD_BUS, PPD_PATH, PPD_IFACE,
         "ActiveProfile", "s", profile],
        timeout=3.0,
    )
    return _get_ppd() == profile


def _on_battery() -> bool:
    out = run_cmd(
        ["busctl", "get-property", "org.freedesktop.UPower",
         "/org/freedesktop/UPower", "org.freedesktop.UPower", "OnBattery"],
        timeout=2.0,
    )
    return (out or "").strip() == "b true"


def _expected_ppd(profile: str) -> str | None:
    return PROFILE_META.get(profile, {}).get("ppd")


def _profile_matches_ppd(profile: str, ppd: str | None) -> bool:
    if not ppd:
        return False
    expected = _expected_ppd(profile)
    if expected and ppd == expected:
        return True
    return profile == "max-power" and ppd == "performance"


def _intermediate_mode(current: str | None, target: str) -> str | None:
    # LLT PowerModeFeature works around firmware that drops direct mode
    # switches: Quiet->Performance goes via Balance, and Custom->other goes
    # via a neighboring mode.
    if current == "low-power" and target == "performance":
        return "balanced"
    if current == "custom":
        return {
            "low-power": "performance",
            "balanced": "low-power",
            "performance": "balanced",
        }.get(target)
    return None


def _sync_omarchy_ppd(profile: str) -> bool:
    ppd = _expected_ppd(profile)
    if not ppd or ppd not in _ppd_profiles():
        return False
    action = "battery" if _on_battery() else "ac"
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    state_file = base / "omarchy" / "powerprofiles" / action
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(ppd + "\n")
    except OSError:
        pass
    return _ppd_set(ppd)


def _sync_legion_from_ppd(ppd: str) -> str | None:
    target = PPD_TO_PROFILE.get(ppd)
    if not target or target not in _choices():
        return None
    current = read_text(PLATFORM_PROFILE)
    if current == target:
        return target
    if current == "max-power" and ppd == "performance":
        return current
    result = _write_profile(target)
    if result["status"] == "success" and read_text(PLATFORM_PROFILE) == target:
        return target
    return None


def sync_power_profiles() -> dict:
    info = {"synced": False, "direction": None}
    if not PLATFORM_PROFILE.exists():
        return info

    profile = read_text(PLATFORM_PROFILE)
    if not profile:
        return info

    ppd = _get_ppd()
    st = plugin_state.load()
    last_profile = st.get("last_platform_profile")
    last_ppd = st.get("last_ppd")

    profile_changed = last_profile is not None and profile != last_profile
    ppd_changed = last_ppd is not None and ppd is not None and ppd != last_ppd
    aligned = _profile_matches_ppd(profile, ppd)

    if profile != "custom" and ppd and not aligned:
        if ppd_changed and not profile_changed:
            if _sync_legion_from_ppd(ppd):
                profile = read_text(PLATFORM_PROFILE) or profile
                info = {"synced": True, "direction": "ppd_to_legion"}
        elif profile_changed and not ppd_changed:
            expected = _expected_ppd(profile)
            if expected and ppd != expected:
                _sync_omarchy_ppd(profile)
                info = {"synced": True, "direction": "legion_to_ppd"}
        elif not aligned:
            expected = _expected_ppd(profile)
            if expected and ppd != expected:
                _sync_omarchy_ppd(profile)
                info = {"synced": True, "direction": "legion_to_ppd"}

    st["last_platform_profile"] = read_text(PLATFORM_PROFILE) or profile
    st["last_ppd"] = _get_ppd()
    plugin_state.save(st)
    return info


def is_custom_mode() -> bool:
    return read_text(PLATFORM_PROFILE) == "custom"


def get_power() -> dict:
    sync_power_profiles()

    raw = read_text(PLATFORM_PROFILE) or "unknown"
    choices = _choices()
    meta = PROFILE_META.get(raw, {
        "id": raw,
        "label": raw.replace("-", " ").title(),
        "desc": "",
        "ppd": None,
    })
    modes = []
    ac = _ac_connected()
    legion_node = _legion_profile_node()
    for profile in choices:
        info = PROFILE_META.get(profile, {
            "id": profile,
            "label": profile.replace("-", " ").title(),
            "desc": "",
            "ppd": None,
        })
        blocked_on_battery = _normalize_mode(profile) in BATTERY_BLOCKED_PROFILES and not ac
        needs_module = profile == "custom" and legion_node is None
        modes.append({
            "id": info["id"],
            "profile": profile,
            "label": info["label"],
            "desc": info["desc"],
            "selected": profile == raw,
            "ppd": info.get("ppd"),
            "blocked_on_battery": blocked_on_battery,
            "needs_module": needs_module,
        })

    ppd = _get_ppd()
    expected_ppd = _expected_ppd(raw) if raw != "custom" else None
    ppd_in_sync = _profile_matches_ppd(raw, ppd)
    effective_ppd = ppd if ppd_in_sync or not expected_ppd else expected_ppd
    return {
        "current_id": meta["id"],
        "current_label": meta["label"],
        "raw_profile": raw,
        "ppd": ppd,
        "effective_ppd": effective_ppd,
        "ppd_label": effective_ppd.replace("-", " ").title() if effective_ppd else None,
        "ppd_in_sync": ppd_in_sync,
        "ac_connected": ac,
        "source": "platform_profile" if PLATFORM_PROFILE.exists() else "none",
        "available_modes": modes,
        "custom": get_custom_limits(),
        "is_custom": raw == "custom",
        "legion_laptop": legion_laptop_loaded(),
    }


def set_power(mode: str) -> dict:
    profile = _normalize_mode(mode)
    if not profile:
        return {"status": "error", "message": f"Unknown power mode: {mode}"}
    if not PLATFORM_PROFILE.exists():
        return {"status": "error", "message": "platform_profile is not available"}
    if profile not in _choices():
        return {"status": "error", "message": f"{profile} is not supported on this BIOS"}
    if profile in BATTERY_BLOCKED_PROFILES and not _ac_connected():
        return {
            "status": "error",
            "message": "Performance, Extreme, and Custom require AC power (Legion Toolkit behavior).",
        }

    meta = PROFILE_META.get(profile, {})

    # Firmware first: only sync PPD after the firmware write succeeds, so a
    # failed firmware write never leaves PPD pointing at a mode we are not in.
    current = read_text(PLATFORM_PROFILE)
    if current == profile:
        if meta.get("ppd"):
            _sync_omarchy_ppd(profile)
        st = plugin_state.load()
        st["last_platform_profile"] = profile
        st["last_ppd"] = _get_ppd()
        plugin_state.save(st)
        return {"status": "success", "mode": meta.get("label", profile), "profile": profile, "method": "ppd"}

    result = _write_profile(profile)
    final = read_text(PLATFORM_PROFILE)
    if result["status"] == "success" and final == profile:
        if meta.get("ppd"):
            _sync_omarchy_ppd(profile)
        result["mode"] = meta.get("label", profile)
        result["profile"] = profile
        st = plugin_state.load()
        st["last_platform_profile"] = profile
        st["last_ppd"] = _get_ppd()
        plugin_state.save(st)
        return result

    # The sysfs write succeeded but firmware did not land on the target
    # (or the write failed). Retry once via an intermediate mode, matching
    # LLT PowerModeFeature's workarounds for firmware that drops direct
    # Quiet->Performance and Custom->other transitions.
    intermediate = _intermediate_mode(current, profile)
    if intermediate and intermediate != profile and intermediate in _choices():
        _write_profile(intermediate)
        time.sleep(0.6)
        result = _write_profile(profile)
        time.sleep(0.2)
        final = read_text(PLATFORM_PROFILE)
        if result["status"] == "success" and final == profile:
            if meta.get("ppd"):
                _sync_omarchy_ppd(profile)
            result["mode"] = meta.get("label", profile)
            result["profile"] = profile
            result["method"] = "via-intermediate"
            st = plugin_state.load()
            st["last_platform_profile"] = profile
            st["last_ppd"] = _get_ppd()
            plugin_state.save(st)
            return result

    if profile == "custom" and _legion_profile_node() is None:
        return {"status": "error", "message": CUSTOM_NEEDS_MODULE}

    if final and final == current and PROFILE_META.get(current, {}).get("ppd") == meta.get("ppd"):
        if meta.get("ppd"):
            _sync_omarchy_ppd(profile)
        current_meta = PROFILE_META.get(current, {})
        st = plugin_state.load()
        st["last_platform_profile"] = current
        st["last_ppd"] = _get_ppd()
        plugin_state.save(st)
        return {
            "status": "success",
            "mode": current_meta.get("label", current),
            "profile": current,
            "method": "ppd-approx",
        }
    if final != profile:
        return {
            "status": "error",
            "message": f"Firmware stayed on {final or 'unknown'} instead of {profile}.",
        }
    return result


def _ppt_attr(name: str) -> dict | None:
    base = FIRMWARE_ATTR / name
    if not (base / "current_value").exists():
        return None
    current = read_text(base / "current_value")
    default = read_text(base / "default_value")
    minimum = read_text(base / "min_value")
    maximum = read_text(base / "max_value")
    friendly = {
        "ppt_pl1_spl": "Sustained power (PL1)",
        "ppt_pl2_sppt": "Boost power (PL2)",
    }
    label = friendly.get(name) or read_text(base / "display_name") or name
    try:
        return {
            "id": name,
            "label": label,
            "current": int(current) if current is not None else None,
            "default_watts": int(default) if default is not None else None,
            "min": int(minimum) if minimum is not None else None,
            "max": int(maximum) if maximum is not None else None,
        }
    except ValueError:
        return None


def get_custom_limits() -> dict:
    return {
        "available": (FIRMWARE_ATTR / "ppt_pl1_spl" / "current_value").exists(),
        "pl1": _ppt_attr("ppt_pl1_spl"),
        "pl2": _ppt_attr("ppt_pl2_sppt"),
    }


def set_ppt(attr: str, value: str) -> dict:
    allowed = {"ppt_pl1_spl", "ppt_pl2_sppt"}
    if attr not in allowed:
        return {"status": "error", "message": f"Unknown PPT attribute: {attr}"}
    try:
        watts = int(str(value).strip())
    except (TypeError, ValueError):
        return {"status": "error", "message": f"Bad PPT value: {value}"}
    if not _ac_connected():
        return {"status": "error", "message": "Custom TDP requires AC power."}
    if not is_custom_mode():
        switch = set_power("custom")
        if switch.get("status") != "success":
            if switch.get("message") == CUSTOM_NEEDS_MODULE:
                return switch
            return {
                "status": "error",
                "message": "Switch to Custom power mode before adjusting TDP limits.",
            }
    path = FIRMWARE_ATTR / attr / "current_value"
    if not path.exists():
        return {"status": "error", "message": "Custom TDP is not exposed on this firmware"}
    result = safe_write(path, str(watts))
    if result["status"] == "success":
        result["ppt"] = attr
        result["watts"] = watts
        return result
    if result.get("reason") in ("Invalid argument", "Device or resource busy"):
        return {"status": "error", "message": CUSTOM_NEEDS_MODULE}
    return result
