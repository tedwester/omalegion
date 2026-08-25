"""Legion power modes via ACPI platform_profile, synced with Omarchy PPD.

Fn+Q / Legion Toolkit Quiet·Balanced·Performance·Extreme·Custom is
/sys/firmware/acpi/platform_profile (lenovo-wmi-gamezone), NOT ideapad fan_mode.
Omarchy's battery panel talks to power-profiles-daemon (power-saver/balanced/
performance). We keep both aligned — Legion mode changes update the battery
panel profile, and battery panel changes update platform_profile.
"""

from __future__ import annotations

from pathlib import Path

from . import state as plugin_state
from .sysfs import read_text, run_cmd, safe_write

PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
PLATFORM_CHOICES = Path("/sys/firmware/acpi/platform_profile_choices")

BATTERY_BLOCKED_PROFILES = frozenset({"performance", "max-power", "custom"})

PPD_TO_PROFILE = {
    "power-saver": "low-power",
    "balanced": "balanced",
    "performance": "performance",
}

# User-facing Legion names -> kernel platform_profile
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


# Kernel profile -> Legion dashboard label
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

FIRMWARE_ATTR = Path("/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes")


def _choices() -> list[str]:
    raw = read_text(PLATFORM_CHOICES)
    if raw:
        return raw.split()
    return ["low-power", "balanced", "performance"]


def _ac_connected() -> bool:
    for ac in Path("/sys/class/power_supply").glob("AC*"):
        if read_text(ac / "online") == "1":
            return True
    return False


def _get_ppd() -> str | None:
    return run_cmd(["powerprofilesctl", "get"], timeout=1.0)


def _expected_ppd(profile: str) -> str | None:
    return PROFILE_META.get(profile, {}).get("ppd")


def _profile_matches_ppd(profile: str, ppd: str | None) -> bool:
    if not ppd:
        return False
    expected = _expected_ppd(profile)
    if expected and ppd == expected:
        return True
    # Extreme maps to the same Omarchy profile as Performance.
    return profile == "max-power" and ppd == "performance"


def _sync_omarchy_ppd(profile: str) -> bool:
    ppd = _expected_ppd(profile)
    if not ppd:
        return False
    run_cmd(["omarchy-powerprofiles-set", "autodetect", ppd], timeout=3.0)
    if _get_ppd() == ppd:
        return True
    run_cmd(["powerprofilesctl", "set", ppd], timeout=3.0)
    return _get_ppd() == ppd


def _sync_legion_from_ppd(ppd: str) -> str | None:
    target = PPD_TO_PROFILE.get(ppd)
    if not target or target not in _choices():
        return None
    current = read_text(PLATFORM_PROFILE)
    if current == target:
        return target
    if current == "max-power" and ppd == "performance":
        return current
    result = safe_write(PLATFORM_PROFILE, target)
    if result["status"] == "success":
        return target
    return None


def sync_power_profiles() -> dict:
    """Bidirectional sync between Legion platform_profile and Omarchy PPD."""
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
            # Omarchy battery panel changed — map to the closest Legion profile.
            if _sync_legion_from_ppd(ppd):
                profile = read_text(PLATFORM_PROFILE) or profile
                info = {"synced": True, "direction": "ppd_to_legion"}
        elif profile_changed and not ppd_changed:
            expected = _expected_ppd(profile)
            if expected and ppd != expected:
                _sync_omarchy_ppd(profile)
                info = {"synced": True, "direction": "legion_to_ppd"}
        elif not aligned:
            # Steady drift (e.g. Fn+Q while PPD daemon stuck) — Legion wins.
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
    for profile in choices:
        info = PROFILE_META.get(profile, {
            "id": profile,
            "label": profile.replace("-", " ").title(),
            "desc": "",
            "ppd": None,
        })
        blocked_on_battery = profile in BATTERY_BLOCKED_PROFILES and not ac
        modes.append({
            "id": info["id"],
            "profile": profile,
            "label": info["label"],
            "desc": info["desc"],
            "selected": profile == raw,
            "ppd": info.get("ppd"),
            "blocked_on_battery": blocked_on_battery,
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

    if meta.get("ppd"):
        _sync_omarchy_ppd(profile)

    current = read_text(PLATFORM_PROFILE)
    if current == profile:
        st = plugin_state.load()
        st["last_platform_profile"] = profile
        st["last_ppd"] = _get_ppd()
        plugin_state.save(st)
        return {"status": "success", "mode": meta.get("label", profile), "profile": profile, "method": "ppd"}

    result = safe_write(PLATFORM_PROFILE, profile)
    if result["status"] == "success":
        result["mode"] = meta.get("label", profile)
        result["profile"] = profile
        st = plugin_state.load()
        st["last_platform_profile"] = profile
        st["last_ppd"] = _get_ppd()
        plugin_state.save(st)
        return result

    if current and PROFILE_META.get(current, {}).get("ppd") == meta.get("ppd"):
        st = plugin_state.load()
        st["last_platform_profile"] = current
        st["last_ppd"] = _get_ppd()
        plugin_state.save(st)
        return {
            "status": "success",
            "mode": meta.get("label", profile),
            "profile": current,
            "method": "ppd-approx",
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
    if not _ac_connected():
        return {"status": "error", "message": "Custom TDP requires AC power."}
    if not is_custom_mode():
        switch = set_power("custom")
        if switch.get("status") != "success":
            return {
                "status": "error",
                "message": "Switch to Custom power mode before adjusting TDP limits.",
            }
    path = FIRMWARE_ATTR / attr / "current_value"
    if not path.exists():
        return {"status": "error", "message": "Custom TDP is not exposed on this firmware"}
    result = safe_write(path, str(int(value)))
    if result["status"] == "success":
        result["ppt"] = attr
        result["watts"] = int(value)
    return result
