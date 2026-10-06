"""Device capability detection, mirroring LLT Utils/Compatibility.cs.

LLT decides feature availability from WMI CapabilityID / SmartFan / LegionZone
versions + DMI model tables. On Linux there is no EnergyDrv WMI, so we probe
the equivalent sysfs / efivar / PCI interfaces and apply the same DMI tables
(MachineTypeMap, ModelKeywordMap, generation parsing, ITS exclusion) so
options appear / hide exactly as they would in LLT.
"""

from __future__ import annotations

import re
from pathlib import Path

from .sysfs import read_text

# --- DMI tables ported from Compatibility.cs ---

MACHINE_TYPE_MAP = {
    "83F0": "Legion_5", "83F1": "Legion_5", "83M0": "Legion_5",
    "83NX": "Legion_5", "83N2": "Legion_5", "83LY": "Legion_5",
    "83DG": "Legion_5", "83EW": "Legion_5", "83EG": "Legion_5",
    "83JJ": "Legion_5", "82RC": "Legion_5", "82RB": "Legion_5",
    "82TB": "Legion_5", "83EF": "Legion_5", "82RE": "Legion_5",
    "82RD": "Legion_5", "83Q7": "Legion_5", "83RW": "Legion_5",
    "83DH": "Legion_Slim_5", "83EX": "Legion_Slim_5", "82Y5": "Legion_Slim_5",
    "82Y9": "Legion_Slim_5", "82YA": "Legion_Slim_5", "83D6": "Legion_Slim_5",
    "83LT": "Legion_Pro_5", "83F3": "Legion_Pro_5", "83DF": "Legion_Pro_5",
    "83F2": "Legion_Pro_5", "83LU": "Legion_Pro_5", "82WM": "Legion_Pro_5",
    "83NN": "Legion_Pro_5", "82WK": "Legion_Pro_5", "82JQ": "Legion_Pro_5",
    "83KY": "Legion_7", "83FD": "Legion_7", "82UH": "Legion_7",
    "82TD": "Legion_7", "82N6": "Legion_7",
    "83RU": "Legion_Pro_7", "83F5": "Legion_Pro_7", "83DE": "Legion_Pro_7",
    "82WR": "Legion_Pro_7", "82WQ": "Legion_Pro_7", "82WS": "Legion_Pro_7",
    "83G0": "Legion_9", "83EY": "Legion_9",
    "83E1": "Legion_Go",
}

MODEL_KEYWORDS = [
    ("IdeaPad Gaming", "IdeaPad_Gaming"),
    ("LOQ", "LOQ"),
    ("IdeaPad", "IdeaPad"),
    ("XiaoXin", "IdeaPad"),
    ("YOGA", "YOGA"),
    ("Lenovo Slim", "Lenovo_Slim"),
    ("ThinkBook", "ThinkBook"),
    ("Legion", "Legion_Legacy"),
    ("Motorola", "Motorola"),
    ("Motobook", "Motorola"),
]

LEGION_SERIES = frozenset({
    "Legion_5", "Legion_Pro_5", "Lenovo_Slim", "Legion_Slim_5",
    "Legion_7", "Legion_Pro_7", "Legion_9", "Legion_Go",
    "LOQ", "Legion_Legacy", "IdeaPad_Gaming",
})


def get_series(model: str, machine_type: str) -> str:
    if machine_type in MACHINE_TYPE_MAP:
        return MACHINE_TYPE_MAP[machine_type]
    for keyword, series in MODEL_KEYWORDS:
        if keyword.lower() in (model or "").lower():
            return series
    return "Unknown"


def is_legion_series(series: str) -> bool:
    return series in LEGION_SERIES


def get_generation(model: str) -> int:
    m = re.search(r"(?<=[A-Z]{3})(\d{1,2})", model or "", re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m = re.search(r"g(\d+)", model or "", re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    for match in re.finditer(r"(?<!\d)\d{1,2}(?!\d)", model or ""):
        try:
            val = int(match.group(0))
        except ValueError:
            continue
        if 14 <= val <= 18:
            continue
        return val
    return 0


def supports_its_mode(model: str) -> bool:
    """Port of Compatibility.GetSupportITSMode: ThinkBook/IdeaPad stack."""
    lower = (model or "").lower()
    if "ideapad gaming" in lower:
        return False
    return any(
        key in lower
        for key in ("ideapad", "thinkbook", "lenovo slim", "motobook", "xiaoxin", "yoga")
    )


def legion_hwmon() -> Path | None:
    """hwmon exposed by legion-laptop (johnfanv2) or lenovo-wmi-gamezone."""
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        name = read_text(hwmon / "name") or ""
        if name in ("legion_hwmon", "legion", "lenovo_wmi", "lenovo-wmi-gamezone"):
            return hwmon
    # legion-laptop platform device path
    for base in Path("/sys/module/legion_laptop/drivers").glob("*/PNP0C09:00"):
        return base
    return None


def legion_platform_base() -> Path | None:
    for base in Path("/sys/module/legion_laptop/drivers").glob("*/PNP0C09:00"):
        if base.exists():
            return base
    return None


def firmware_attr_base() -> Path | None:
    root = Path("/sys/class/firmware-attributes")
    if not root.exists():
        return None
    for child in sorted(root.iterdir()):
        if child.is_dir():
            return child
    return None


def _firmware_attr_names() -> set[str]:
    base = firmware_attr_base()
    if base is None:
        return set()
    attrs = base / "attributes"
    if not attrs.exists():
        return set()
    try:
        return {p.name for p in attrs.iterdir() if p.is_dir()}
    except OSError:
        return set()


def get_capabilities() -> dict:
    """Probe all availability flags. Mirrors LLT MachineInformation.Properties."""
    vendor = read_text(Path("/sys/class/dmi/id/sys_vendor")) or ""
    machine_type = (read_text(Path("/sys/class/dmi/id/product_name")) or "").strip()
    # LLT uses product_version as Model ("Legion Pro 5 16ARX8"); product_name
    # as 4-char MTM ("83F2"). Some kernels swap them, so try both.
    model = (read_text(Path("/sys/class/dmi/id/product_version")) or "").strip()
    family = (read_text(Path("/sys/class/dmi/id/product_family")) or "").strip()
    if len(machine_type) > 6 and not model:
        model = machine_type
    if not model:
        model = family or "Unknown"
    generation = get_generation(model)
    series = get_series(model, machine_type)
    legion = is_legion_series(series)
    its = supports_its_mode(model)

    has_platform_profile = Path("/sys/firmware/acpi/platform_profile").exists()
    choices_raw = read_text(Path("/sys/firmware/acpi/platform_profile_choices")) or ""
    choices = choices_raw.split() if choices_raw else []

    names = _firmware_attr_names()
    hwmon_base = legion_platform_base()
    has_legion_module = hwmon_base is not None
    has_fan_curve = False
    has_fan_fullspeed = False
    has_powerlimits = False
    has_cpu_oc = False
    has_gpu_oc_attr = False
    if hwmon_base is not None:
        has_fan_fullspeed = (hwmon_base / "fan_fullspeed").exists()
        has_powerlimits = any((hwmon_base / n).exists() for n in (
            "ppt_pl1_spl", "ppt_pl2_sppt", "cpu_powerlimit",
        ))
        has_cpu_oc = (hwmon_base / "cpu_oc").exists()
        has_gpu_oc_attr = (hwmon_base / "gpu_oc").exists()
        # hwmon fan-curve points: pwmY_auto_pointZ_pwm under hwmon dir
        try:
            for hw in Path(str(hwmon_base)).glob("hwmon/hwmon*"):
                if next(hw.glob("pwm*_auto_point*_pwm"), None) is not None:
                    has_fan_curve = True
                    break
            if not has_fan_curve:
                for hw in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
                    if (read_text(hw / "name") or "") == "legion_hwmon":
                        if next(hw.glob("pwm*_auto_point*_pwm"), None) is not None:
                            has_fan_curve = True
                            break
        except (OSError, StopIteration):
            pass

    has_ppt_attrs = any(n.startswith("ppt_") for n in names) or (
        (Path("/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/ppt_pl1_spl/current_value").exists())
    )
    has_graphics_attr = "GraphicsDevice" in names
    has_usb_attr = any("usb" in n.lower() and "charg" in n.lower() for n in names)
    has_overdrive_attr = "OverDrive" in names or "overdrive" in {n.lower() for n in names}

    # GPU presence (LLT SupportsGSync / SupportsIGPUMode need WMI; on Linux
    # probe PCI + drm mux like Compatibility fallback).
    has_nvidia = any(
        (read_text(dev / "vendor") or "").lower().strip() == "0x10de"
        for dev in Path("/sys/bus/pci/devices").glob("*")
    ) if Path("/sys/bus/pci/devices").exists() else False
    has_amd_dgpu = False  # discrete AMD rare on Legion; keep for completeness
    internal_edp = any(True for _ in Path("/sys/class/drm").glob("card*-eDP-*")) if Path("/sys/class/drm").exists() else False

    # efivars (LLT FlipToStart / BootLogo use UEFI vars)
    efivars = Path("/sys/firmware/efi/efivars")
    has_flip_efivar = False
    has_bootlogo_efivar = False
    if efivars.exists():
        try:
            for entry in efivars.iterdir():
                low = entry.name.lower()
                if low.startswith("fbswif-"):
                    has_flip_efivar = True
                if low.startswith("lbldesp-") or low.startswith("lbldvc-"):
                    has_bootlogo_efivar = True
        except OSError:
            pass

    # NPU for AI mode (LLT SupportsAIMode needs GetIntelligentSubMode)
    has_npu = False
    try:
        if Path("/sys/class/accel").exists():
            has_npu = any(True for _ in Path("/sys/class/accel").glob("accel*"))
    except OSError:
        pass

    # Overdrive exclusion: Legion 7 / Pro 7 Gen>=10 (LLT GetIsOverdriverSupported)
    overdrive_excluded = series in ("Legion_7", "Legion_Pro_7") and generation >= 10

    # GodMode platform mapping (simplified, sysfs-grounded):
    # LLT: ITS -> NonGaming; GodMode bit -> Legion/LegacyLegion.
    # Linux: ITS models -> nongaming; ppt/fan-curve/powerlimits -> legion custom.
    if its:
        godmode_platform = "nongaming"
    elif has_ppt_attrs or has_powerlimits or has_fan_curve or "custom" in choices:
        godmode_platform = "legion"
    elif has_platform_profile and legion:
        godmode_platform = "legion-lite"  # PPT via RAPL only
    else:
        godmode_platform = None

    supports_extreme = ("max-power" in choices) or (
        legion and has_legion_module and generation >= 8
    )

    # Keyboard lighting detection (LLT exclusions: Legion 7 Gen6, old BIOS)
    kbd_leds = []
    try:
        for led in Path("/sys/class/leds").glob("*"):
            n = led.name.lower()
            if "kbd" in n or "keyboard" in n:
                kbd_leds.append(led.name)
    except OSError:
        pass
    lighting_excluded = series == "Legion_7" and generation == 6

    return {
        "vendor": vendor,
        "machine_type": machine_type,
        "model": model,
        "family": family,
        "generation": generation,
        "series": series,
        "is_legion": legion,
        "supports_its_mode": its,
        "has_platform_profile": has_platform_profile,
        "platform_choices": choices,
        "supports_extreme": supports_extreme,
        "godmode_platform": godmode_platform,
        "supports_custom": godmode_platform is not None,
        "has_legion_module": has_legion_module,
        "has_fan_curve": has_fan_curve,
        "has_fan_fullspeed": has_fan_fullspeed,
        "has_powerlimits": has_powerlimits or has_ppt_attrs,
        "has_cpu_oc_attr": has_cpu_oc,
        "has_gpu_oc_attr": has_gpu_oc_attr,
        "has_graphics_attr": has_graphics_attr,
        "has_usb_attr": has_usb_attr,
        "has_overdrive_attr": has_overdrive_attr,
        "has_nvidia": has_nvidia,
        "has_internal_display": internal_edp,
        "supports_gsync": has_nvidia and internal_edp and not its,
        "supports_igpu_mode": has_nvidia and (has_graphics_attr or internal_edp),
        "supports_overdrive": internal_edp and not overdrive_excluded and (has_overdrive_attr or legion),
        "overdrive_excluded": overdrive_excluded,
        "has_flip_efivar": has_flip_efivar,
        "has_bootlogo_efivar": has_bootlogo_efivar,
        "supports_flip_to_start": has_flip_efivar,
        "supports_boot_logo": has_bootlogo_efivar,
        "has_npu": has_npu,
        "supports_ai_mode": has_npu and not its,
        "kbd_leds": kbd_leds,
        "lighting_excluded": lighting_excluded,
        "supports_white_backlight": bool(kbd_leds) and not lighting_excluded,
    }
