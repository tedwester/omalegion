from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import state as plugin_state
from .sysfs import ideapad_dir, read_text, run_cmd, safe_write, safe_write_bytes

IDEAPAD = ideapad_dir()
LEGION_TOUCHPAD = Path("/sys/devices/platform/legion/touchpad")

FBSWIF_VAR = Path(
    "/sys/firmware/efi/efivars/FBSWIF-d743491e-f484-4952-a87d-8d5dd189b70c"
)


def _lua_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _touchpad_names() -> list[str]:
    out = run_cmd(["hyprctl", "devices", "-j"], timeout=2.0)
    if not out:
        return []
    try:
        devices = json.loads(out)
    except (ValueError, TypeError):
        return []
    names = []
    for group in ("mice", "keyboards", "tablets", "touch"):
        for dev in devices.get(group, []) or []:
            name = dev.get("name") or ""
            if not isinstance(name, str) or not name:
                continue
            # Device names are embedded into a Lua snippet; reject control
            # characters so a hostile/comprised compositor reply cannot break
            # out of the string context.
            if any(ord(c) < 32 or ord(c) == 127 for c in name):
                continue
            if "touchpad" in name.lower() and name not in names:
                names.append(name)
    return names


def _hypr_eval(lua: str) -> bool:
    if "\n" in lua or "\r" in lua or "\x00" in lua:
        return False
    result = run_cmd(["hyprctl", "eval", lua], timeout=3.0)
    return result is not None and "ok" in result.lower()


def get_touchpad() -> dict:
    if LEGION_TOUCHPAD.exists():
        return {
            "available": True,
            "names": [],
            "locked": read_text(LEGION_TOUCHPAD) == "0",
            "source": "firmware",
            "reason": None,
        }
    names = _touchpad_names()
    st = plugin_state.load()
    return {
        "available": bool(names),
        "names": names,
        "locked": bool(st.get("touchpad_lock")) if names else False,
        "source": "session",
        "reason": None if names else "No touchpad exposed by Hyprland",
    }


def set_touchpad_lock(locked: bool) -> dict:
    if LEGION_TOUCHPAD.exists():
        result = safe_write(LEGION_TOUCHPAD, "0" if locked else "1")
        if result["status"] == "success":
            result["touchpad_lock"] = bool(locked)
            result["message"] = "Touchpad off" if locked else "Touchpad on"
            st = plugin_state.load()
            st["touchpad_lock"] = bool(locked)
            plugin_state.save(st)
            for name in _touchpad_names():
                _hypr_eval(
                    f'hl.device({{ name = "{_lua_escape(name)}", '
                    f'enabled = {"false" if locked else "true"} }})'
                )
        return result
    names = _touchpad_names()
    if not names:
        return {"status": "error", "message": "No touchpad found via hyprctl"}
    ok = True
    for name in names:
        lua = (
            f'hl.device({{ name = "{_lua_escape(name)}", '
            f'enabled = {"false" if locked else "true"} }})'
        )
        ok = _hypr_eval(lua) and ok
    if not ok:
        return {"status": "error", "message": "hyprctl rejected the touchpad change"}
    st = plugin_state.load()
    st["touchpad_lock"] = bool(locked)
    plugin_state.save(st)
    return {
        "status": "success",
        "touchpad_lock": bool(locked),
        "message": "Touchpad off" if locked else "Touchpad on",
    }


def _has_pipewire() -> bool:
    return shutil.which("pactl") is not None or shutil.which("wpctl") is not None


def _pactl_short(kind: str) -> list[tuple[int, str]]:
    out = run_cmd(["pactl", "list", "short", kind], timeout=2.0)
    if not out:
        return []
    items = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            name = parts[1]
            if kind == "sources" and name.endswith(".monitor"):
                continue
            items.append((int(parts[0]), name))
    return items


def _pactl_mute(kind: str, index: int) -> bool | None:
    noun = "source" if kind == "sources" else "sink"
    out = run_cmd(["pactl", f"get-{noun}-mute", str(index)], timeout=2.0)
    if not out:
        return None
    match = re.search(r"mute:\s*(yes|no)", out.strip().lower())
    if match:
        return match.group(1) == "yes"
    return None


def get_microphone() -> dict:
    sources = _pactl_short("sources")
    if not _has_pipewire() or not sources:
        return {"available": False, "muted": False, "reason": "No PipeWire capture source"}
    states = [_pactl_mute("sources", idx) for idx, _ in sources]
    states = [s for s in states if s is not None]
    if not states:
        return {"available": False, "muted": False, "reason": "Could not query sources"}
    return {"available": True, "muted": all(states), "inputs": len(sources)}


def set_microphone_mute(muted: bool) -> dict:
    sources = _pactl_short("sources")
    if not sources:
        return {"status": "error", "message": "No microphone source found"}
    ok = True
    for idx, _ in sources:
        res = run_cmd(
            ["pactl", "set-source-mute", str(idx), "1" if muted else "0"], timeout=2.0
        )
        ok = (res is not None) and ok
    if not ok:
        return {"status": "error", "message": "Failed to mute microphone"}
    return {
        "status": "success",
        "mic_muted": bool(muted),
        "message": "Microphone muted" if muted else "Microphone live",
    }


def _sink_volume_percent(index: int) -> int | None:
    out = run_cmd(["pactl", "get-sink-volume", str(index)], timeout=2.0)
    if not out:
        return None
    found = [int(m) for m in re.findall(r"(\d+)%", out)]
    return max(found) if found else None


def get_speaker() -> dict:
    sinks = _pactl_short("sinks")
    if not _has_pipewire() or not sinks:
        return {"available": False, "muted": False, "volume": None,
                "reason": "No PipeWire sink"}
    states = [_pactl_mute("sinks", idx) for idx, _ in sinks]
    states = [s for s in states if s is not None]
    vols = [_sink_volume_percent(idx) for idx, _ in sinks]
    vols = [v for v in vols if v is not None]
    if not states:
        return {"available": False, "muted": False, "volume": None,
                "reason": "Could not query sinks"}
    return {
        "available": True,
        "muted": all(states),
        "volume": round(sum(vols) / len(vols)) if vols else None,
        "outputs": len(sinks),
    }


def set_speaker_mute(muted: bool) -> dict:
    sinks = _pactl_short("sinks")
    if not sinks:
        return {"status": "error", "message": "No audio sink found"}
    ok = True
    for idx, _ in sinks:
        res = run_cmd(
            ["pactl", "set-sink-mute", str(idx), "1" if muted else "0"], timeout=2.0
        )
        ok = (res is not None) and ok
    if not ok:
        return {"status": "error", "message": "Failed to mute speakers"}
    return {
        "status": "success",
        "speaker_muted": bool(muted),
        "message": "Speakers muted" if muted else "Speakers live",
    }


def set_speaker_volume(percent: int) -> dict:
    sinks = _pactl_short("sinks")
    if not sinks:
        return {"status": "error", "message": "No audio sink found"}
    percent = max(0, min(150, int(percent)))
    ok = True
    for idx, _ in sinks:
        res = run_cmd(
            ["pactl", "set-sink-volume", str(idx), f"{percent}%"], timeout=2.0
        )
        ok = (res is not None) and ok
    if not ok:
        return {"status": "error", "message": "Failed to set volume"}
    return {"status": "success", "volume": percent, "message": f"Volume {percent}%"}


def _read_fbswif() -> bytes | None:
    try:
        if FBSWIF_VAR.is_file():
            return FBSWIF_VAR.read_bytes()
    except OSError:
        pass
    return None


def get_flip_to_start() -> dict:
    raw = _read_fbswif()
    if raw is None:
        return {"available": False, "enabled": False,
                "reason": "FBSWIF UEFI variable not present"}
    payload = raw[4:]
    return {
        "available": True,
        "enabled": len(payload) >= 1 and payload[0] == 1,
    }


def set_flip_to_start(enabled: bool) -> dict:
    raw = _read_fbswif()
    if raw is None:
        return {"status": "error", "message": "FBSWIF UEFI variable not present"}
    attrs, payload = raw[:4], raw[4:]
    if len(payload) < 1:
        return {"status": "error", "message": "Unexpected FBSWIF layout"}
    new_payload = bytes([1 if enabled else 0]) + payload[1:]
    result = safe_write_bytes(FBSWIF_VAR, attrs + new_payload)
    if result["status"] == "success":
        result["flip_to_start"] = bool(enabled)
        result["message"] = (
            "Flip to Start on — opening the lid boots the laptop"
            if enabled else "Flip to Start off"
        )
    return result


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

    info["touchpad"] = get_touchpad()
    info["microphone"] = get_microphone()
    info["speaker"] = get_speaker()
    info["flip_to_start"] = get_flip_to_start()
    info["camera"] = {
        "available": False,
        "reason": "camera_power is read-only on this firmware",
    }
    return info


def set_fn_lock(enabled: bool) -> dict:
    if not IDEAPAD.exists():
        return {"status": "error", "message": "ideapad_acpi not found"}
    result = safe_write(IDEAPAD / "fn_lock", "1" if enabled else "0")
    if result["status"] == "success":
        result["fn_lock"] = bool(enabled)
        result["message"] = "Fn Lock on" if enabled else "Fn Lock off"
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
