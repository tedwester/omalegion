from __future__ import annotations

import array
import fcntl
import glob
import os
import re
import struct
import subprocess
from pathlib import Path

REPORT_SIZE = 960
# _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06/0x07, REPORT_SIZE): (3<<30)|(size<<16)|('H'<<8)|nr
HIDIOCSFEATURE = 0xC0004806 | (REPORT_SIZE << 16)
HIDIOCGFEATURE = 0xC0004807 | (REPORT_SIZE << 16)

HELPER = "/usr/local/bin/omalegion-write"

MARKER = b"\x06\x89\xff"

OP_EFFECT_CHANGE = 0xCB
OP_GET_BRIGHTNESS = 0xCD
OP_BRIGHTNESS = 0xCE
OP_PROFILE_CHANGE = 0xC8
OP_PROFILE = 0xCA
OP_COMPATIBILITY = 0xD1
OP_KEY_COUNT = 0xC4
OP_KEY_PAGE = 0xC5

EFFECTS = {
    "static": 11,
    "screw-rainbow": 1,
    "rainbow-wave": 2,
    "color-change": 3,
    "color-pulse": 4,
    "color-wave": 5,
    "smooth": 6,
    "rain": 7,
    "ripple": 8,
    "type": 12,
}

COLORS = {
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 128, 0),
    "purple": (128, 0, 255),
}

ALL_KEY = 0x0065

_last_brightness = 5


def find_device() -> str | None:
    from . import layouts, machine

    info = machine.get_machine()
    family = machine.keyboard_pid_family(info["series"], info["generation"] or 0)
    for hidraw in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = Path(hidraw, "device", "uevent").read_text().upper()
            if "048D" not in uevent:
                continue
            families = {int(pid, 16) & 0xFF00 for pid in re.findall(r"C[0-9A-F]{3}", uevent)}
            if family not in families:
                continue
            desc = Path(hidraw, "device", "report_descriptor").read_bytes()
            if MARKER not in desc:
                continue
            return f"/dev/{Path(hidraw).name}"
        except OSError:
            continue
    return None


def get_layout() -> dict:
    from . import layouts, machine

    keymap = get_keymap()
    codes = set()
    if keymap.get("available"):
        # Matrix codes only: additional (secondary-page) codes live outside
        # the matrix by definition, so they must not fail layout matching.
        codes = {c for r in keymap["rows"] for c in r if c}
    if 0xA9 in codes:
        name = "jis"
    elif 0xA8 in codes:
        name = "iso"
    else:
        name = "ansi"
    info = machine.get_machine()
    if info.get("keyboard_24zone"):
        name = "24zone" if "24zone" in layouts.LAYOUTS else name
    layout = layouts.LAYOUTS.get(name, {})
    rows = layout.get("rows", [])
    island = layout.get("island", [])
    known = {c for r in rows for _, c in r} | {cell["code"] for cell in island}
    return {"name": name, "rows": rows, "island": island,
            "matches": bool(codes) and codes <= known}


def _direct_set(node: str, data: bytes) -> bool:
    try:
        fd = os.open(node, os.O_RDWR | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        buf = array.array("B", bytes(data[:REPORT_SIZE]).ljust(REPORT_SIZE, b"\x00"))
        fcntl.ioctl(fd, HIDIOCSFEATURE, buf)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _direct_get(node: str, report_id: int = 0x07) -> bytes | None:
    try:
        fd = os.open(node, os.O_RDWR | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        buf = array.array("B", [report_id] + [0] * (REPORT_SIZE - 1))
        fcntl.ioctl(fd, HIDIOCGFEATURE, buf)
        return bytes(buf)
    except OSError:
        return None
    finally:
        os.close(fd)


def _helper(args: list[str], timeout: float = 15.0) -> str | None:
    try:
        result = subprocess.run(
            ["sudo", "-n", HELPER] + args,
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _set_report(node: str, data: bytes) -> bool:
    if os.geteuid() == 0 and _direct_set(node, data):
        return True
    if os.geteuid() == 0:
        return False
    padded = bytes(data[:REPORT_SIZE]).ljust(REPORT_SIZE, b"\x00")
    return _helper(["hid-set", node, padded.hex()]) is not None


def _get_report(node: str, report_id: int = 0x07) -> bytes | None:
    direct = _direct_get(node, report_id)
    if direct is not None and any(direct[1:]):
        return direct
    hexdata = _helper(["hid-get", node, str(report_id)])
    if not hexdata:
        return None
    try:
        raw = bytes.fromhex(hexdata)
    except ValueError:
        return None
    if len(raw) != REPORT_SIZE or not any(raw[1:]):
        return None
    return raw


def _req(op: int, payload: bytes = b"") -> bytes:
    return bytes([0x07, op, 0xC0, 0x03]) + bytes(payload)


def get_keymap() -> dict:
    from . import state as plugin_state

    st = plugin_state.load()
    cached = st.get("kbd_keymap")
    if isinstance(cached, dict) and cached.get("rows") and "additional" in cached:
        return {"available": True, **{k: cached[k] for k in ("width", "height", "rows", "additional") if k in cached}}
    node = find_device()
    if not node:
        return {"available": False}
    if not _set_report(node, _req(OP_KEY_COUNT, bytes([0x07]))):
        return {"available": False}
    count = _get_report(node)
    if count is None:
        return {"available": False}
    height, width = count[5], count[6]
    if not 0 < width <= 32 or not 0 < height <= 32:
        return {"available": False}
    rows = []
    for y in range(height):
        if not _set_report(node, _req(OP_KEY_PAGE, bytes([0x07, y]))):
            return {"available": False}
        page = _get_report(node)
        if page is None:
            return {"available": False}
        row = []
        for x in range(width):
            off = 6 + x * 3
            row.append(page[off + 1] | (page[off + 2] << 8))
        rows.append(row)
    # LLT also reads the secondary page (param 8): extra keycodes outside the
    # main matrix. Tolerate failure so RGB keeps working if it is absent.
    additional: list[int] = []
    if _set_report(node, _req(OP_KEY_PAGE, bytes([0x08, 0x00]))):
        page = _get_report(node)
        if page is not None:
            for x in range(width):
                off = 6 + x * 3
                code = page[off + 1] | (page[off + 2] << 8)
                if code:
                    additional.append(code)
    result = {"width": width, "height": height, "rows": rows, "additional": additional}
    st["kbd_keymap"] = result
    plugin_state.save(st)
    return {"available": True, **result}


def get_state() -> dict:
    node = find_device()
    if not node:
        return {"available": False}
    if not _set_report(node, _req(OP_COMPATIBILITY)):
        return {"available": False}
    resp = _get_report(node)
    if resp is None or resp[4] != 0:
        return {"available": False}
    if not _set_report(node, _req(OP_GET_BRIGHTNESS)):
        return {"available": False}
    bright = _get_report(node)
    if bright is None:
        return {"available": False}
    profile = None
    if _set_report(node, _req(OP_PROFILE)):
        prof = _get_report(node)
        if prof is not None:
            profile = prof[4]
    keymap = get_keymap()
    from . import state as plugin_state

    st = plugin_state.load()
    last = st.get("kbd_last") if isinstance(st.get("kbd_last"), dict) else None
    seen = st.get("kbd_profile_seen")
    if profile is not None and seen is not None and profile != seen:
        cfg = None
        slots = st.get("kbd_slots")
        if isinstance(slots, dict):
            cand = slots.get(str(profile))
            if isinstance(cand, dict) and cand.get("effect"):
                cfg = cand
        if cfg is not None and _apply(node, profile, cfg):
            last = cfg
    if profile is not None and profile != seen:
        st["kbd_profile_seen"] = profile
        plugin_state.save(st)

    layout = get_layout()
    return {
        "available": True,
        "on": bright[4] > 0,
        "brightness": bright[4],
        "profile": profile,
        "last": last,
        "layout": layout,
        "effects": sorted(EFFECTS),
        "colors": sorted(COLORS),
        "keymap": keymap if keymap.get("available") else None,
    }


def set_profile(profile: int) -> dict:
    node = find_device()
    if not node:
        return {"status": "error", "message": "Spectrum keyboard not found"}
    profile = max(0, min(6, int(profile)))
    if not _set_report(node, _req(OP_PROFILE_CHANGE, bytes([profile]))):
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    if not _set_report(node, _req(OP_PROFILE)):
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    actual = _get_report(node)
    if actual is None or actual[4] != profile:
        return {"status": "error", "message": "Lighting slot did not change"}
    from . import state as plugin_state

    st = plugin_state.load()
    st["kbd_profile_seen"] = profile
    plugin_state.save(st)
    return {"status": "success", "profile": profile,
            "message": f"Lighting slot {profile}"}


def set_brightness(level: int) -> dict:
    from . import state as plugin_state

    node = find_device()
    if not node:
        return {"status": "error", "message": "Spectrum keyboard not found"}
    level = max(0, min(9, int(level)))
    if not _set_report(node, _req(OP_BRIGHTNESS, bytes([level]))):
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    if not _set_report(node, _req(OP_GET_BRIGHTNESS)):
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    actual = _get_report(node)
    if actual is None or actual[4] != level:
        return {"status": "error", "message": "Keyboard brightness did not change"}
    if level > 0:
        st = plugin_state.load()
        st["kbd_brightness"] = level
        plugin_state.save(st)
    return {"status": "success", "brightness": level,
            "message": f"Keyboard brightness {level}" if level else "Keyboard lighting off"}


def _all_keys() -> list[int] | None:
    keymap = get_keymap()
    if not keymap.get("available"):
        return None
    keys = [c for r in keymap["rows"] for c in r if c]
    keys += [c for c in keymap.get("additional", []) if c]
    return keys


def _effect_blob(effect: str, color: tuple[int, int, int] | None, keycodes: list[int], speed: int = 2, direction: int = 0) -> bytes:
    etype = EFFECTS[effect]
    colors = [color] if color else []
    color_mode = 0x02 if colors else 0x01
    header = bytes([0x06, 0x01, etype, 0x02, speed, 0x03, 0, 0x04, direction, 0x05, color_mode, 0x06, 0x00])
    blob = bytes([1]) + header + bytes([len(colors)])
    for component in colors:
        blob += bytes(component)
    blob += bytes([len(keycodes)])
    for kc in keycodes:
        blob += struct.pack("<H", kc)
    return blob


def set_power(on: bool) -> dict:
    from . import state as plugin_state

    if not on:
        return set_brightness(0)
    level = int(plugin_state.load().get("kbd_brightness") or 5)
    result = set_brightness(level)
    if result["status"] != "success":
        return result
    last = plugin_state.load().get("kbd_last")
    if isinstance(last, dict) and last.get("effect"):
        return set_effect(last["effect"], last.get("color"),
                          int(last.get("speed") or 2), int(last.get("direction") or 0))
    return result


def _send_effect(node: str, profile: int, effect: str, rgb: tuple[int, int, int] | None, keycodes: list[int], speed: int = 2, direction: int = 0) -> bool:
    payload = bytes([profile, 0x01, 0x01]) + _effect_blob(effect, rgb, keycodes, speed, direction)
    # LLT patches the u16 size at offset 2 as (total bytes - 4), not the
    # fixed 960 (0x03C0). Here that equals len(payload): 3 profile bytes +
    # effect bytes (the 4 header bytes are excluded).
    header = bytes([0x07, OP_EFFECT_CHANGE]) + struct.pack("<H", len(payload))
    return _set_report(node, header + payload)


def _current_profile(node: str) -> int | None:
    if not _set_report(node, _req(OP_PROFILE)):
        return None
    resp = _get_report(node)
    return resp[4] if resp is not None else None


def _apply(node: str, profile: int, cfg: dict) -> bool:
    rgb = None
    if cfg.get("color"):
        rgb = COLORS.get(str(cfg["color"]).lower())
        if rgb is None:
            return False
    try:
        keys = _all_keys()
        if not keys:
            return False
        return _send_effect(node, profile, cfg["effect"],
                           rgb, keys,
                           max(0, min(3, int(cfg.get("speed", 2)))),
                           max(0, min(4, int(cfg.get("direction", 0)))))
    except (TypeError, ValueError, KeyError):
        return False


def _store(profile: int | None, effect: str, color: str | None, speed: int, direction: int) -> None:
    from . import state as plugin_state

    st = plugin_state.load()
    cfg = {"effect": effect, "color": color, "speed": speed, "direction": direction}
    slots = st.get("kbd_slots")
    if not isinstance(slots, dict):
        slots = {}
    if profile is not None:
        slots[str(profile)] = cfg
        st["kbd_profile_seen"] = profile
    st["kbd_slots"] = slots
    st["kbd_last"] = dict(cfg)
    plugin_state.save(st)


def set_effect(effect: str, color: str | None = None, speed: int | None = None, direction: int | None = None) -> dict:
    from . import state as plugin_state

    if effect not in EFFECTS:
        return {"status": "error", "message": f"Unknown effect: {effect}"}
    if effect == "static" and not color:
        color = "white"
    rgb = None
    if color:
        rgb = COLORS.get(color.lower())
        if rgb is None:
            return {"status": "error", "message": f"Unknown color: {color}"}
    try:
        st = plugin_state.load()
        last = st.get("kbd_last") if isinstance(st.get("kbd_last"), dict) else {}
        if speed is None:
            speed = last.get("speed", 2)
        if direction is None:
            direction = last.get("direction", 0)
        speed = max(0, min(3, int(speed)))
        direction = max(0, min(4, int(direction)))
    except (TypeError, ValueError):
        return {"status": "error", "message": "Bad speed or direction"}
    node = find_device()
    if not node:
        return {"status": "error", "message": "Spectrum keyboard not found"}
    keys = _all_keys()
    if not keys:
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    profile = _current_profile(node)
    if profile is None:
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    if not _send_effect(node, profile, effect, rgb, keys, speed, direction):
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    _store(profile, effect, color, speed, direction)
    return {"status": "success", "effect": effect,
            "message": f"Keyboard effect: {effect}" + (f" {color}" if color else "")}


def apply_last(speed: int | None = None, direction: int | None = None) -> dict:
    from . import state as plugin_state

    st = plugin_state.load()
    last = st.get("kbd_last")
    if not isinstance(last, dict) or not last.get("effect"):
        return {"status": "error", "message": "Pick an effect first"}
    if speed is None:
        try:
            speed = int(last.get("speed") or 2)
        except (TypeError, ValueError):
            speed = 2
    if direction is None:
        try:
            direction = int(last.get("direction") or 0)
        except (TypeError, ValueError):
            direction = 0
    return set_effect(last["effect"], last.get("color"), speed, direction)


def set_keys(keycodes: list[int], color: str) -> dict:
    rgb = COLORS.get((color or "").lower())
    if rgb is None:
        return {"status": "error", "message": f"Unknown color: {color}"}
    node = find_device()
    if not node:
        return {"status": "error", "message": "Spectrum keyboard not found"}
    try:
        keys = [int(kc) for kc in list(keycodes)[:512] if 0 < int(kc) < 65535]
    except (TypeError, ValueError):
        return {"status": "error", "message": "Bad key selection"}
    if not keys:
        return {"status": "error", "message": "No keys selected"}
    profile = _current_profile(node)
    if profile is None:
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    if not _send_effect(node, profile, "static", rgb, keys):
        return {"status": "error", "message": "Spectrum keyboard not accessible"}
    return {"status": "success", "keys": len(keys),
            "message": f"{len(keys)} keys painted {color}"}
