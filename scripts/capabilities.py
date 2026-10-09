#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

LEGION_DEV = Path("/sys/devices/platform/legion")
IDEAPAD = Path("/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00")
FBSWIF = Path("/sys/firmware/efi/efivars/FBSWIF-d743491e-f484-4952-a87d-8d5dd189b70c")


def read(path: Path | str) -> str | None:
    try:
        p = Path(path)
        if p.is_file():
            return p.read_text().strip()
    except OSError:
        pass
    return None


def machine() -> dict:
    from legion.machine import get_machine

    try:
        return get_machine()
    except OSError:
        return {}


def modules() -> dict:
    return {
        name: (Path("/sys/module") / name).exists()
        for name in (
            "legion_laptop",
            "lenovo_wmi_gamezone",
            "lenovo_wmi_other",
            "ideapad_laptop",
        )
    }


def legion_nodes() -> dict:
    if not LEGION_DEV.is_dir():
        return {"present": False, "nodes": []}
    nodes = sorted(p.name for p in LEGION_DEV.iterdir() if p.is_file())
    return {"present": True, "nodes": nodes}


def firmware_attributes() -> list[str]:
    base = Path("/sys/class/firmware-attributes")
    attrs: list[str] = []
    for driver in sorted(base.glob("*")):
        names = driver / "attributes"
        if names.is_dir():
            attrs.extend(sorted(p.name for p in names.iterdir()))
    return attrs


def platform_profile() -> dict:
    acpi = Path("/sys/firmware/acpi/platform_profile")
    choices_path = Path("/sys/firmware/acpi/platform_profile_choices")
    legion_profile = None
    legion_choices: list[str] = []
    for choices in sorted((LEGION_DEV / "platform-profile").glob("*/choices")):
        node = choices.parent
        if read(node / "name") == "lenovo-legion" and (node / "profile").exists():
            legion_profile = str(node / "profile")
            raw = read(choices)
            legion_choices = raw.split() if raw else []
            break
    raw_acpi = read(choices_path)
    return {
        "acpi_node": acpi.exists(),
        "acpi_choices": raw_acpi.split() if raw_acpi else [],
        "legion_node": legion_profile,
        "legion_choices": legion_choices,
        "custom_enterable": legion_profile is not None,
    }


def fans() -> dict:
    legion = None
    classic = 0
    pwm = 0
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        name = read(hwmon / "name")
        if name == "legion_hwmon":
            legion = str(hwmon)
            continue
        for i in range(1, 7):
            if (hwmon / f"fan{i}_input").exists():
                classic += 1
                if (hwmon / f"pwm{i}_enable").exists():
                    pwm += 1
    curve = False
    if legion:
        curve = (Path(legion) / "pwm1_auto_point1_pwm").exists()
    return {
        "legion_hwmon": legion,
        "legion_curve": curve,
        "classic_fans": classic,
        "classic_pwm": pwm,
    }


def battery() -> dict:
    bats = sorted(Path("/sys/class/power_supply").glob("BAT*"))
    charge_types: list[str] = []
    if bats and (bats[0] / "charge_types").exists():
        raw = read(bats[0] / "charge_types") or ""
        for token in raw.replace("[", "").replace("]", "").split():
            if token not in charge_types:
                charge_types.append(token)
    return {
        "present": bool(bats),
        "charge_types": charge_types,
        "ideapad_conservation": (IDEAPAD / "conservation_mode").exists(),
        "ideapad_usb": (IDEAPAD / "usb_charging").exists(),
        "legion_conservation": (LEGION_DEV / "battery_conservation").exists(),
        "legion_rapidcharge": (LEGION_DEV / "rapidcharge").exists(),
        "legion_powerchargemode": (LEGION_DEV / "powerchargemode").exists(),
    }


def input_dev() -> dict:
    kbd = any(
        "kbd" in led.name.lower() or "keyboard" in led.name.lower()
        for led in Path("/sys/class/leds").glob("*")
    )
    return {
        "fn_lock": (IDEAPAD / "fn_lock").exists(),
        "kbd_backlight": kbd,
        "legion_touchpad": (LEGION_DEV / "touchpad").exists(),
        "legion_winkey": (LEGION_DEV / "winkey").exists(),
        "flip_to_start": FBSWIF.is_file(),
        "camera_power": (IDEAPAD / "camera_power").exists(),
    }


def display() -> dict:
    return {
        "gsync": (LEGION_DEV / "gsync").exists(),
        "igpumode": (LEGION_DEV / "igpumode").exists(),
        "gsync_support": read(LEGION_DEV / "issupportgsync"),
        "igpumode_support": read(LEGION_DEV / "issupportigpumode"),
    }


def lighting() -> dict:
    leds_dir = LEGION_DEV / "leds"
    leds = sorted(p.name for p in leds_dir.glob("*")) if leds_dir.is_dir() else []
    return {"legion_leds": leds}


def session() -> dict:
    touchpads: list[str] = []
    try:
        out = subprocess.run(
            ["hyprctl", "devices", "-j"],
            capture_output=True, text=True, timeout=3.0,
        )
        if out.returncode == 0:
            for group in ("mice", "keyboards", "tablets", "touch"):
                for dev in json.loads(out.stdout).get(group, []) or []:
                    name = dev.get("name") or ""
                    if "touchpad" in name.lower() and name not in touchpads:
                        touchpads.append(name)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    sources = sinks = 0
    try:
        out = subprocess.run(
            ["pactl", "list", "short"],
            capture_output=True, text=True, timeout=3.0,
        )
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    if parts[1].startswith("alsa_input") or "input" in parts[1]:
                        if not parts[1].endswith(".monitor"):
                            sources += 1
                    if "output" in parts[1] or "sink" in parts[1]:
                        sinks += 1
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"hyprland_touchpads": touchpads, "audio_sources": sources, "audio_sinks": sinks}


def collect() -> dict:
    return {
        "machine": machine(),
        "modules": modules(),
        "legion": legion_nodes(),
        "firmware_attributes": firmware_attributes(),
        "platform_profile": platform_profile(),
        "fans": fans(),
        "battery": battery(),
        "input": input_dev(),
        "display": display(),
        "lighting": lighting(),
        "session": session(),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
