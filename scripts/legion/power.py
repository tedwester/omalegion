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
    try:
        from .capabilities import get_capabilities as _caps

        caps = _caps()
    except Exception:
        caps = {}
    st = plugin_state.load()
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
        "supports_extreme": bool(caps.get("supports_extreme", "max-power" in choices)),
        "supports_custom": bool(caps.get("supports_custom", False)),
        "godmode_platform": caps.get("godmode_platform"),
        "godmode_presets": st.get("godmode_presets") or {},
        "godmode_active_preset": st.get("godmode_active_preset"),
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


def _attr_roots() -> list[Path]:
    roots: list[Path] = []
    fw = Path("/sys/class/firmware-attributes")
    if fw.exists():
        try:
            for child in sorted(fw.iterdir()):
                attrs = child / "attributes"
                if attrs.exists():
                    roots.append(attrs)
        except OSError:
            pass
    # legion-laptop platform device also exposes powerlimit knobs next to
    # fan_fullspeed; treat it as an attribute root when present.
    try:
        for base in Path("/sys/module/legion_laptop/drivers").glob("*/PNP0C09:00"):
            if base.exists():
                roots.append(base)
    except OSError:
        pass
    if FIRMWARE_ATTR.exists() and FIRMWARE_ATTR not in roots:
        roots.append(FIRMWARE_ATTR)
    return roots


def _find_attr(name: str) -> Path | None:
    for root in _attr_roots():
        direct = root / name / "current_value"
        if direct.exists():
            return root / name
        plain = root / name
        try:
            if plain.is_file():
                return plain
        except OSError:
            continue
    return None


def _read_attr_limit(attr_path: Path) -> dict | None:
    """Read one tunable limit, mirroring LLT StepperValue {value,min,max,step,default}."""
    if attr_path.is_file():
        raw = read_text(attr_path)
        try:
            return {
                "id": attr_path.name,
                "label": attr_path.name.replace("_", " ").title(),
                "current": int(raw) if raw is not None else None,
                "default_watts": None,
                "min": None,
                "max": None,
                "unit": "W" if "ppt" in attr_path.name or "power" in attr_path.name else "",
            }
        except (ValueError, TypeError):
            return None
    base = attr_path
    if not (base / "current_value").exists():
        return None
    current = read_text(base / "current_value")
    default = read_text(base / "default_value")
    minimum = read_text(base / "min_value")
    maximum = read_text(base / "max_value")
    step = read_text(base / "scalar_increment")
    disp = read_text(base / "display_name")
    friendly = {
        "ppt_pl1_spl": "Sustained power (PL1)",
        "ppt_pl2_sppt": "Boost power (PL2)",
        "ppt_pl1": "Sustained power (PL1)",
        "ppt_pl2": "Boost power (PL2)",
        "cpu_temp_limit": "CPU temperature limit",
        "gpu_temp_limit": "GPU temperature limit",
        "gpu_ctgp": "GPU configurable TGP",
        "gpu_ppab": "GPU Dynamic Boost (PPAB)",
    }
    label = friendly.get(base.name) or disp or base.name.replace("_", " ").title()

    def to_int(v: str | None) -> int | None:
        if v is None:
            return None
        try:
            return int(str(v).split()[0])
        except (ValueError, IndexError):
            return None

    unit = ""
    low = (disp or base.name).lower()
    if "temp" in low or "thermal" in low:
        unit = "°C"
    elif "ppt" in base.name or "power" in low or low.endswith("w"):
        unit = "W"
    step_v = to_int(step)
    if step_v is not None and step_v <= 0:
        step_v = None
    return {
        "id": base.name,
        "label": label,
        "current": to_int(current),
        "default_watts": to_int(default),
        "min": to_int(minimum),
        "max": to_int(maximum),
        # No fabricated step: None means firmware gave no increment, so any
        # in-range integer is accepted (LLT hides step-less capabilities;
        # on Linux the node is still writable so we expose it honestly).
        "step": step_v,
        "unit": unit,
    }


# Candidate knobs in LLT GodMode order. Only those present on this firmware
# are exposed — exactly like LLT skips capabilities with Step==0/Steps==0.
CUSTOM_CANDIDATES = [
    "ppt_pl1_spl", "ppt_pl1", "cpu_pl1", "pl1_spl",
    "ppt_pl2_sppt", "ppt_pl2", "cpu_pl2", "pl2_sppt",
    "ppt_pl3", "cpu_peak_power", "cpu_cross_loading",
    "cpu_pl2_tau", "pl2_tau", "cpu_tau",
    "cpu_temp_limit", "cpu_temperature_limit",
    "gpu_ctgp", "gpu_tgp", "gpu_ppab", "gpu_power_boost", "gpu_dynamic_boost",
    "gpu_tpp_offset", "gpu_tpp", "tpp_offset",
    "gpu_temp_limit", "gpu_temperature_limit",
    "apu_sppt", "apu_slow_limit",
]


def get_custom_limits() -> dict:
    found: dict[str, dict] = {}
    for name in CUSTOM_CANDIDATES:
        node = _find_attr(name)
        if node is None:
            continue
        info = _read_attr_limit(node)
        if info and info.get("current") is not None:
            found[name] = info
    # Also sweep any other ppt_*/powerlimit_* the firmware exposes so new
    # BIOS revisions appear automatically (LLT uses live capability ranges).
    for root in _attr_roots():
        try:
            children = [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            continue
        for child in children:
            n = child.name
            if n in found or n in CUSTOM_CANDIDATES:
                continue
            ln = n.lower()
            if n.startswith("ppt_") or "powerlimit" in n or "tdp" in n or "temp_limit" in n \
                    or "tau" in ln or "tpp" in ln or "boost" in ln:
                info = _read_attr_limit(child)
                if info and info.get("current") is not None:
                    found[n] = info
    # RAPL fallback (Legion-lite): sustained/boost via intel-rapl when no
    # firmware attributes exist. Read-only unless writable.
    if not found:
        try:
            for rapl in sorted(Path("/sys/class/powercap").glob("intel-rapl:*")):
                name_f = read_text(rapl / "name") or rapl.name
                if "package" not in name_f.lower() and rapl.name != "intel-rapl:0":
                    continue
                for con in sorted(rapl.glob("constraint_*_power_limit_uw")):
                    try:
                        uw = int((read_text(con) or "0").split()[0])
                    except ValueError:
                        continue
                    key = f"rapl_{con.name}"
                    found[key] = {
                        "id": key,
                        "label": f"RAPL {con.name} ({name_f})",
                        "current": round(uw / 1_000_000, 1),
                        "default_watts": None,
                        "min": 5,
                        "max": 150,
                        "step": 1,
                        "unit": "W",
                        "path": str(con),
                    }
                if found:
                    break
        except OSError:
            pass
    pl1 = found.get("ppt_pl1_spl") or found.get("ppt_pl1") or next(
        (v for k, v in found.items() if "pl1" in k.lower() or "spl" in k.lower()), None
    )
    pl2 = found.get("ppt_pl2_sppt") or found.get("ppt_pl2") or next(
        (v for k, v in found.items() if "pl2" in k.lower() or "sppt" in k.lower()), None
    )
    return {
        "available": bool(found),
        "limits": found,
        "pl1": pl1,
        "pl2": pl2,
    }


def set_ppt(attr: str, value: str) -> dict:
    node = _find_attr(attr)
    # RAPL path stored with explicit path
    rapl_path: Path | None = None
    limits = get_custom_limits().get("limits", {})
    if attr in limits and limits[attr].get("path"):
        rapl_path = Path(str(limits[attr]["path"]))
        node = None
    allowed_names = set(CUSTOM_CANDIDATES) | set(limits.keys())
    if node is None and rapl_path is None:
        if attr not in allowed_names:
            return {"status": "error", "message": f"Unknown PPT attribute: {attr}"}
        return {"status": "error", "message": "Custom TDP is not exposed on this firmware"}
    if not _ac_connected():
        return {"status": "error", "message": "Custom TDP requires AC power."}
    if not is_custom_mode():
        switch = set_power("custom")
        if switch.get("status") != "success":
            return {
                "status": "error",
                "message": "Switch to Custom power mode before adjusting TDP limits.",
            }
    try:
        wanted = int(float(str(value)))
    except ValueError:
        return {"status": "error", "message": f"Invalid value: {value}"}
    if rapl_path is not None:
        info = limits[attr]
        lo, hi = info.get("min") or 5, info.get("max") or 150
        if not (lo <= wanted <= hi):
            return {"status": "error", "message": f"{wanted} W out of range {lo}–{hi} W"}
        result = safe_write(rapl_path, str(wanted * 1_000_000))
        if result["status"] == "success":
            result["ppt"] = attr
            result["watts"] = wanted
        return result
    assert node is not None
    info = _read_attr_limit(node)
    if info:
        lo, hi = info.get("min"), info.get("max")
        if lo is not None and hi is not None and not (lo <= wanted <= hi):
            return {"status": "error", "message": f"{wanted} out of range {lo}–{hi}"}
        step = info.get("step")
        if step and step > 1 and lo is not None:
            # LLT StepperValue snaps to the firmware increment.
            wanted = lo + round((wanted - lo) / step) * step
            wanted = max(lo, min(hi, wanted))
    target = node / "current_value" if (node / "current_value").exists() else node
    result = safe_write(target, str(wanted))
    if result["status"] == "success":
        result["ppt"] = attr
        result["watts"] = wanted
    return result


def list_godmode_presets() -> dict:
    st = plugin_state.load()
    presets = st.get("godmode_presets") or {}
    return {"status": "success", "presets": presets, "active": st.get("godmode_active_preset")}


def save_godmode_preset(name: str, values: dict) -> dict:
    if not name or not name.strip():
        return {"status": "error", "message": "Preset name is required"}
    st = plugin_state.load()
    presets = dict(st.get("godmode_presets") or {})
    presets[name.strip()] = dict(values or {})
    st["godmode_presets"] = presets
    st["godmode_active_preset"] = name.strip()
    plugin_state.save(st)
    return {"status": "success", "preset": name.strip(), "message": f"Preset '{name.strip()}' saved"}


def delete_godmode_preset(name: str) -> dict:
    st = plugin_state.load()
    presets = dict(st.get("godmode_presets") or {})
    if name not in presets:
        return {"status": "error", "message": f"Unknown preset: {name}"}
    del presets[name]
    st["godmode_presets"] = presets
    if st.get("godmode_active_preset") == name:
        st["godmode_active_preset"] = None
    plugin_state.save(st)
    return {"status": "success", "preset": name, "message": f"Preset '{name}' deleted"}


def apply_godmode_preset(name: str) -> dict:
    st = plugin_state.load()
    presets = st.get("godmode_presets") or {}
    values = presets.get(name)
    if not values:
        return {"status": "error", "message": f"Unknown preset: {name}"}
    if not is_custom_mode():
        switch = set_power("custom")
        if switch.get("status") != "success":
            return {"status": "error", "message": "Switch to Custom power mode first."}
    applied, failed = [], []
    for attr, val in values.items():
        res = set_ppt(str(attr), str(val))
        (applied if res.get("status") == "success" else failed).append(str(attr))
    if failed and not applied:
        return {"status": "error", "message": f"Could not apply: {', '.join(failed)}"}
    if not failed:
        # LLT only raises PresetChanged after full success — don't mark a
        # partially applied preset active.
        st["godmode_active_preset"] = name
        plugin_state.save(st)
    return {
        "status": "success",
        "preset": name,
        "applied": applied,
        "failed": failed,
        "message": f"Preset '{name}' applied" + (f" (skipped {', '.join(failed)})" if failed else ""),
    }
