"""Fans and thermal sensors."""

from __future__ import annotations

from pathlib import Path

from .power import is_custom_mode
from .sysfs import read_text, run_cmd, safe_write


def _hwmon_named(name: str) -> Path | None:
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        if read_text(hwmon / "name") == name:
            return hwmon
    return None


def _temp_c(path: Path) -> float | None:
    raw = read_text(path)
    if raw and raw.lstrip("-").isdigit():
        return round(int(raw) / 1000, 1)
    return None


def _read_fan(hwmon: Path, index: int) -> dict | None:
    fan_input = hwmon / f"fan{index}_input"
    if not fan_input.exists():
        return None
    rpm_raw = read_text(fan_input)
    pwm = read_text(hwmon / f"pwm{index}")
    pwm_enable = read_text(hwmon / f"pwm{index}_enable")
    name = read_text(hwmon / "name") or hwmon.name
    has_pwm = (hwmon / f"pwm{index}_enable").exists()
    return {
        "index": index,
        "rpm": int(rpm_raw) if rpm_raw and rpm_raw.isdigit() else None,
        "pwm_percent": round((int(pwm) / 255) * 100) if pwm and pwm.isdigit() else None,
        "mode": "manual" if pwm_enable == "1" else "auto",
        "has_control": has_pwm,
        "hwmon_name": name,
        "hwmon_path": str(hwmon),
        "label": f"{name} fan {index}",
    }


def _collect_fans() -> list[dict]:
    fans = []
    seen = set()
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        for index in range(1, 7):
            info = _read_fan(hwmon, index)
            if not info:
                continue
            key = (info["hwmon_path"], info["index"])
            if key in seen:
                continue
            seen.add(key)
            fans.append(info)
    return fans


def _primary_fan(fans: list[dict]) -> dict | None:
    if not fans:
        return None
    for fan in fans:
        if fan.get("has_control"):
            return fan
    return fans[0]


def _custom_mode_required() -> dict | None:
    if not is_custom_mode():
        return {
            "status": "error",
            "message": "Manual fan control requires Custom power mode (Legion Toolkit behavior).",
        }
    return None


def get_fans() -> dict:
    all_fans = _collect_fans()
    primary = _primary_fan(all_fans)

    if not primary:
        return {
            "rpm": None,
            "mode": "unknown",
            "has_control": False,
            "hwmon_name": None,
            "fans": [],
            "custom_mode_required": True,
        }

    return {
        "rpm": primary.get("rpm"),
        "pwm_percent": primary.get("pwm_percent"),
        "mode": primary.get("mode", "unknown"),
        "has_control": primary.get("has_control", False),
        "hwmon_name": primary.get("hwmon_name"),
        "hwmon_path": primary.get("hwmon_path"),
        "fan_index": primary.get("index", 1),
        "fans": all_fans,
        "custom_mode_required": True,
        "manual_available": primary.get("has_control") and is_custom_mode(),
    }


def set_fan_mode(auto: bool, fan_index: int | None = None) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked

    info = get_fans()
    if not info.get("has_control"):
        return {"status": "error", "message": "Manual fan control needs the legion-laptop module"}

    index = fan_index or info.get("fan_index") or 1
    path = Path(info["hwmon_path"]) / f"pwm{index}_enable"
    result = safe_write(path, "2" if auto else "1")
    if result["status"] == "success":
        result["mode"] = "auto" if auto else "manual"
    return result


def set_fan_speed(percent: int, fan_index: int | None = None) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked

    info = get_fans()
    if not info.get("has_control"):
        return {"status": "error", "message": "Manual fan control needs the legion-laptop module"}

    percent = max(0, min(100, int(percent)))
    index = fan_index or info.get("fan_index") or 1
    base = Path(info["hwmon_path"])
    r1 = safe_write(base / f"pwm{index}_enable", "1")
    r2 = safe_write(base / f"pwm{index}", str(int((percent / 100) * 255)))
    if r1["status"] == "success" and r2["status"] == "success":
        return {"status": "success", "percent": percent}
    return {"status": "error", "message": "Failed to set fan speed"}


def get_thermals() -> dict:
    temps = {
        "cpu_package": None,
        "gpu_temp": None,
        "nvme_temp": None,
        "memory_temp": None,
    }

    coretemp = _hwmon_named("coretemp")
    if coretemp:
        hottest = None
        for f in sorted(coretemp.glob("temp*_input")):
            t = _temp_c(f)
            if t is None:
                continue
            label = read_text(coretemp / f.name.replace("_input", "_label")) or f.stem
            if "package" in label.lower() or "tdie" in label.lower():
                temps["cpu_package"] = t
            hottest = t if hottest is None else max(hottest, t)
        if temps["cpu_package"] is None:
            temps["cpu_package"] = hottest

    nvme = _hwmon_named("nvme")
    if nvme:
        temps["nvme_temp"] = _temp_c(nvme / "temp1_input")

    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        if read_text(hwmon / "name") == "spd5118":
            t = _temp_c(hwmon / "temp1_input")
            if t is not None:
                temps["memory_temp"] = max(temps["memory_temp"] or 0, t)

    gpu_out = run_cmd(
        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
        timeout=1.5,
    )
    if gpu_out:
        try:
            temps["gpu_temp"] = float(gpu_out.splitlines()[0].strip())
        except ValueError:
            pass

    return temps
