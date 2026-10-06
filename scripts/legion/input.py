"""Fn-lock, keyboard backlight, touchpad, mic/speaker.

LLT has FnLock (+SmartFnLock), TouchpadLock (precision/WMI), WinKey lock,
Microphone mute+LED, Speaker mute+volume+LED. On Linux:
  FnLock -> ideapad_acpi/fn_lock (no SmartFnLock hook; documented)
  Backlight -> leds kbd_backlight (white 3-level Off/Low/High like LLT WhiteKB)
  Touchpad -> gsettings (GNOME) or hyprctl (Hyprland/Omarchy)
  Mic/Speaker -> wpctl / pactl (PipeWire/Pulse)
  WinKey/Camera -> no safe Linux equivalent; reported unsupported like LLT
  would hide the feature.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .sysfs import read_text, run_cmd, safe_write

IDEAPAD = Path("/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00")

# LLT FnLockFeature.TranslateStateAsync: polarity is swapped on modern
# non-Legion series (IdeaPad / YOGA / ThinkBook / Motorola / Unknown).
# Legion + LOQ use the raw value.
_INVERTED_FNLOCK_SERIES = frozenset({
    "IdeaPad", "IdeaPad_Gaming", "YOGA", "ThinkBook", "Motorola", "Unknown",
})


def _fnlock_inverted() -> bool:
    try:
        from .capabilities import get_series
    except Exception:
        return False
    try:
        mtm = read_text(Path("/sys/class/dmi/id/product_name")) or ""
        model = read_text(Path("/sys/class/dmi/id/product_version")) or mtm
        return get_series(model or "", mtm or "") in _INVERTED_FNLOCK_SERIES
    except Exception:
        return False


def _kbd_led() -> Path | None:
    best: Path | None = None
    for led in Path("/sys/class/leds").glob("*"):
        name = led.name.lower()
        if "kbd" in name or "keyboard" in name:
            # Prefer platform/ideapad leds over input::*capslock etc.
            if best is None or "input" not in best.name.lower():
                best = led
            if "platform" in name or "ideapad" in name or "legion" in name:
                return led
    return best


def _touchpad_backend() -> str:
    if shutil.which("gsettings"):
        return "gsettings"
    if shutil.which("hyprctl"):
        return "hyprctl"
    return "none"


def _touchpad_enabled() -> bool | None:
    if shutil.which("gsettings"):
        out = run_cmd(
            ["gsettings", "get", "org.gnome.desktop.peripherals.touchpad", "send-events"],
            timeout=1.5,
        )
        if out:
            v = out.strip().strip("'\"")
            if v in ("enabled", "disabled", "disabled-on-external-mouse"):
                return v == "enabled" or v == "disabled-on-external-mouse"
    return None


def _pactl_endpoints(list_cmd: list[str]) -> list[str]:
    """All source/sink names via `pactl list short`. LLT mutes all endpoints."""
    out = run_cmd(list_cmd, timeout=1.5)
    names = []
    if out:
        for line in out.splitlines():
            bits = line.split()
            if len(bits) >= 2:
                names.append(bits[1])
    return names


def _audio_muted(kind: str) -> bool | None:
    # LLT Microphone/Speaker state is AND over ALL endpoints: muted only if
    # every endpoint is muted. Mirror that instead of default-only.
    # kind: @DEFAULT_AUDIO_SOURCE@ (mic) / @DEFAULT_AUDIO_SINK@ (speaker)
    is_source = "SOURCE" in kind
    if shutil.which("pactl"):
        names = _pactl_endpoints(["pactl", "list", "short", "sources" if is_source else "sinks"])
        states = []
        for name in names:
            out = run_cmd(
                ["pactl", "get-source-mute" if is_source else "get-sink-mute", name],
                timeout=1.5,
            )
            if out:
                states.append("yes" in out.lower())
        if states:
            return all(states)
    if shutil.which("wpctl"):
        out = run_cmd(["wpctl", "get-volume", kind], timeout=1.5)
        if out:
            return "[MUTED]" in out
    return None


def _set_mute_all(is_source: bool, muted: bool) -> bool:
    """Mute/unmute every endpoint (LLT SetState mutes all). Returns True if any backend worked."""
    import subprocess

    target = "1" if muted else "0"
    worked = False
    if shutil.which("pactl"):
        names = _pactl_endpoints(["pactl", "list", "short", "sources" if is_source else "sinks"])
        for name in names:
            try:
                r = subprocess.run(
                    ["pactl", "set-source-mute" if is_source else "set-sink-mute", name, target],
                    capture_output=True, text=True, timeout=5,
                )
                worked = worked or r.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        if worked or names:
            return worked
    if shutil.which("wpctl"):
        try:
            r = subprocess.run(
                ["wpctl", "set-mute",
                 "@DEFAULT_AUDIO_SOURCE@" if is_source else "@DEFAULT_AUDIO_SINK@", target],
                capture_output=True, text=True, timeout=5,
            )
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    return False


def _audio_volume() -> int | None:
    if shutil.which("wpctl"):
        out = run_cmd(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], timeout=1.5)
        if out:
            try:
                # "Volume: 0.45" or "Volume: 0.45 [MUTED]"
                bits = out.replace("Volume:", "").replace("[MUTED]", "").strip().split()
                return int(round(float(bits[0]) * 100))
            except (ValueError, IndexError):
                pass
    if shutil.which("pactl"):
        out = run_cmd(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], timeout=1.5)
        if out:
            # "... / 45% / ..." — take the first percent (LLT clamps 0–100).
            import re

            m = re.search(r"(\d+)%", out)
            if m:
                try:
                    return max(0, min(100, int(m.group(1))))
                except ValueError:
                    pass
    return None


def get_input() -> dict:
    info = {
        "fn_lock": False,
        "fn_lock_available": IDEAPAD.exists() and (IDEAPAD / "fn_lock").exists(),
        "backlight_available": False,
        "backlight_brightness": None,
        "backlight_max": None,
        "backlight_levels": [],
        "touchpad_available": False,
        "touchpad_enabled": None,
        "mic_muted": None,
        "mic_available": False,
        "speaker_muted": None,
        "speaker_volume": None,
        "speaker_available": False,
        "winkey_available": False,
        "winkey_note": "WinKey lock is WMI-only in LLT. No safe Linux equivalent — use compositor keybinds.",
        "smart_fnlock_supported": False,
        "smart_fnlock_note": "SmartFnLock (temp unlock on Ctrl/Shift/Alt) is a Windows low-level hook. Not available on Linux.",
    }
    if IDEAPAD.exists():
        raw = read_text(IDEAPAD / "fn_lock") == "1"
        info["fn_lock"] = (not raw) if _fnlock_inverted() else raw
        info["fn_lock_inverted"] = _fnlock_inverted()

    led = _kbd_led()
    if led is not None:
        br = read_text(led / "brightness")
        mx = read_text(led / "max_brightness")
        try:
            b = int(br) if br and br.strip().lstrip("-").isdigit() else None
            m = int(mx) if mx and mx.strip().isdigit() else 2
        except ValueError:
            b, m = None, 2
        info["backlight_available"] = True
        info["backlight_brightness"] = b
        info["backlight_max"] = m
        info["backlight_path"] = str(led)
        # LLT WhiteKeyboard states Off/Low/High map to 0/1/2 when max==2;
        # OneLevel white (max==1) is Off/On like LLT OneLevelWhiteKeyboard.
        if m == 2:
            info["backlight_levels"] = [
                {"id": 0, "label": "Off", "selected": b == 0},
                {"id": 1, "label": "Low", "selected": b == 1},
                {"id": 2, "label": "High", "selected": b == 2},
            ]
        elif m == 1:
            info["backlight_levels"] = [
                {"id": 0, "label": "Off", "selected": b == 0},
                {"id": 1, "label": "On", "selected": b == 1},
            ]
        else:
            info["backlight_levels"] = [
                {"id": i, "label": str(i), "selected": b == i} for i in range(m + 1)
            ]

    tp = _touchpad_enabled()
    info["touchpad_available"] = _touchpad_backend() != "none"
    info["touchpad_enabled"] = tp

    mic = _audio_muted("@DEFAULT_AUDIO_SOURCE@")
    info["mic_available"] = mic is not None
    info["mic_muted"] = mic

    spk = _audio_muted("@DEFAULT_AUDIO_SINK@")
    info["speaker_available"] = spk is not None
    info["speaker_muted"] = spk
    info["speaker_volume"] = _audio_volume()
    return info


def set_fn_lock(enabled: bool) -> dict:
    if not IDEAPAD.exists() or not (IDEAPAD / "fn_lock").exists():
        return {"status": "error", "message": "Fn Lock is not exposed (ideapad_acpi missing)"}
    # Translate back through the series polarity (LLT ToInternal).
    target = (not enabled) if _fnlock_inverted() else bool(enabled)
    result = safe_write(IDEAPAD / "fn_lock", "1" if target else "0")
    if result["status"] == "success":
        result["fn_lock"] = bool(enabled)
    return result


def set_backlight(level: int) -> dict:
    led = _kbd_led()
    if led is None:
        return {"status": "error", "message": "Keyboard backlight is not available"}
    mx_raw = read_text(led / "max_brightness")
    try:
        mx = int(mx_raw) if mx_raw and mx_raw.strip().isdigit() else 2
        value = max(0, min(mx, int(level)))
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid backlight level"}
    result = safe_write(led / "brightness", str(value))
    if result["status"] == "success":
        result["backlight"] = value
    return result


def set_touchpad(enabled: bool) -> dict:
    if shutil.which("gsettings"):
        val = "enabled" if enabled else "disabled"
        import subprocess

        try:
            r = subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.peripherals.touchpad", "send-events", val],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return {"status": "success", "touchpad": bool(enabled)}
        except (OSError, subprocess.TimeoutExpired):
            pass
    if shutil.which("hyprctl"):
        # hyprctl keyword input:touchpad:disable 0/1 — needs reload-safe call
        import subprocess

        try:
            r = subprocess.run(
                ["hyprctl", "keyword", "input:touchpad:disable", "0" if enabled else "1"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return {"status": "success", "touchpad": bool(enabled)}
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"status": "error", "message": "Touchpad control needs gsettings or hyprctl"}


def set_mic_mute(muted: bool) -> dict:
    if _set_mute_all(is_source=True, muted=bool(muted)):
        return {"status": "success", "mic_muted": bool(muted)}
    return {"status": "error", "message": "Microphone mute needs wpctl or pactl"}


def set_speaker_mute(muted: bool) -> dict:
    if _set_mute_all(is_source=False, muted=bool(muted)):
        return {"status": "success", "speaker_muted": bool(muted)}
    return {"status": "error", "message": "Speaker mute needs wpctl or pactl"}


def set_speaker_volume(percent: int) -> dict:
    """LLT SpeakerFeature.SetVolumeAsync equivalent (0–100, clamped)."""
    import subprocess

    try:
        pct = max(0, min(100, int(percent)))
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid volume (0–100)"}
    if shutil.which("wpctl"):
        try:
            r = subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{pct}%"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return {"status": "success", "speaker_volume": pct}
        except (OSError, subprocess.TimeoutExpired):
            pass
    if shutil.which("pactl"):
        try:
            r = subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                return {"status": "success", "speaker_volume": pct}
        except (OSError, subprocess.TimeoutExpired):
            pass
    return {"status": "error", "message": "Speaker volume needs wpctl or pactl"}
