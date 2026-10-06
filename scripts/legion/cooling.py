"""Fans and thermal sensors.

LLT GodMode fan control is a 10-point FanTable + FanFullSpeed bool, only in
GodMode/Custom. On Linux the equivalent is legion-laptop (johnfanv2):
  /sys/module/legion_laptop/drivers/platform:legion/PNP0C09:00/fan_fullspeed
  /sys/.../hwmon/hwmon*/pwmY_auto_pointZ_{pwm,temp,temp_hyst}
  /sys/kernel/debug/legion/fancurve (read-only table)
We expose exactly what the kernel exposes, gated like LLT capabilities.
"""

from __future__ import annotations

from pathlib import Path

from . import state as plugin_state
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


def _legion_base() -> Path | None:
    try:
        for base in Path("/sys/module/legion_laptop/drivers").glob("*/PNP0C09:00"):
            if base.exists():
                return base
    except OSError:
        pass
    return None


def _legion_hwmon() -> Path | None:
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        if (read_text(hwmon / "name") or "") == "legion_hwmon":
            return hwmon
    base = _legion_base()
    if base is not None:
        try:
            for hw in sorted((base / "hwmon").glob("hwmon*")):
                return hw
            for hw in sorted(base.glob("hwmon/hwmon*")):
                return hw
        except OSError:
            pass
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
    try:
        rpm = int(rpm_raw) if rpm_raw and rpm_raw.strip().isdigit() else None
    except ValueError:
        rpm = None
    try:
        pwm_pct = round((int(pwm) / 255) * 100) if pwm and pwm.strip().isdigit() else None
    except ValueError:
        pwm_pct = None
    # hwmon convention: 0 = full-speed/disabled, 1 = manual, 2 = auto.
    if pwm_enable == "1":
        mode = "manual"
    elif pwm_enable == "2":
        mode = "auto"
    elif pwm_enable == "0":
        mode = "fullspeed"
    else:
        mode = "unknown"
    return {
        "index": index,
        "rpm": rpm,
        "pwm_percent": pwm_pct,
        "mode": mode,
        "has_control": has_pwm,
        "hwmon_name": name,
        "hwmon_path": str(hwmon),
        "label": f"{name} fan {index}",
    }


def _collect_fans() -> list[dict]:
    fans = []
    seen = set()
    hwmons = sorted(Path("/sys/class/hwmon").glob("hwmon*"))
    legion = _legion_hwmon()
    if legion is not None and legion not in hwmons:
        hwmons.append(legion)
    for hwmon in hwmons:
        try:
            if not hwmon.exists():
                continue
        except OSError:
            continue
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
        if fan.get("hwmon_name") == "legion_hwmon" and fan.get("has_control"):
            return fan
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


def _fullspeed_path() -> Path | None:
    base = _legion_base()
    if base is not None and (base / "fan_fullspeed").exists():
        return base / "fan_fullspeed"
    return None


def get_fans() -> dict:
    all_fans = _collect_fans()
    primary = _primary_fan(all_fans)
    fullspeed_p = _fullspeed_path()
    fullspeed = None
    if fullspeed_p is not None:
        fullspeed = read_text(fullspeed_p) == "1"
    curve = get_fan_curve()

    if not primary:
        return {
            "rpm": None,
            "mode": "unknown",
            "has_control": False,
            "hwmon_name": None,
            "fans": [],
            "custom_mode_required": False,
            "manual_available": False,
            "has_curve": curve.get("available", False),
            "has_fullspeed": fullspeed_p is not None,
            "fullspeed": fullspeed,
            "curve": curve,
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
        "manual_available": bool(primary.get("has_control")) and is_custom_mode(),
        "has_curve": curve.get("available", False),
        "has_fullspeed": fullspeed_p is not None,
        "fullspeed": fullspeed,
        "curve": curve,
    }


def set_fan_mode(auto: bool, fan_index: int | None = None) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked

    info = get_fans()
    if not info.get("has_control"):
        return {"status": "error", "message": "Manual fan control needs the legion-laptop module"}

    index = fan_index or info.get("fan_index") or 1
    # Resolve hwmon that actually owns this index
    hwmon_path = None
    for fan in info.get("fans", []):
        if fan.get("index") == index and fan.get("has_control"):
            hwmon_path = fan.get("hwmon_path")
            break
    hwmon_path = hwmon_path or info.get("hwmon_path")
    if not hwmon_path:
        return {"status": "error", "message": "No controllable fan found"}
    path = Path(hwmon_path) / f"pwm{index}_enable"
    if not path.exists():
        return {"status": "error", "message": f"Fan {index} has no pwm control on this device"}
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

    try:
        percent = max(0, min(100, int(percent)))
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid fan percent"}
    index = fan_index or info.get("fan_index") or 1
    hwmon_path = None
    for fan in info.get("fans", []):
        if fan.get("index") == index and fan.get("has_control"):
            hwmon_path = fan.get("hwmon_path")
            break
    hwmon_path = hwmon_path or info.get("hwmon_path")
    base = Path(hwmon_path)
    if not (base / f"pwm{index}").exists():
        return {"status": "error", "message": f"Fan {index} has no pwm control on this device"}
    r1 = safe_write(base / f"pwm{index}_enable", "1")
    r2 = safe_write(base / f"pwm{index}", str(int(round((percent / 100) * 255))))
    if r1["status"] == "success" and r2["status"] == "success":
        return {"status": "success", "percent": percent, "fan": index}
    return {"status": "error", "message": "Failed to set fan speed"}


def set_fan_fullspeed(enabled: bool) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked
    path = _fullspeed_path()
    if path is None:
        return {"status": "error", "message": "Fan full-speed is not exposed (legion-laptop missing)"}
    result = safe_write(path, "1" if enabled else "0")
    if result["status"] == "success":
        result["fullspeed"] = bool(enabled)
        st = plugin_state.load()
        st["fan_fullspeed"] = bool(enabled)
        plugin_state.save(st)
    return result


def get_fan_curve() -> dict:
    """Read legion-laptop 10-point curve points that exist on this device."""
    hwmon = _legion_hwmon()
    if hwmon is None:
        return {"available": False, "points": [], "reason": "legion-laptop hwmon not found"}
    points: list[dict] = []
    try:
        pwm_files = sorted(hwmon.glob("pwm*_auto_point*_pwm"))
    except OSError:
        pwm_files = []
    if not pwm_files:
        return {"available": False, "points": [], "reason": "No pwm_auto_point nodes on this firmware"}
    # Group by (pwmY, pointZ)
    import re

    grouped: dict[tuple[int, int], dict] = {}
    for pwm_f in pwm_files:
        m = re.match(r"pwm(\d+)_auto_point(\d+)_pwm", pwm_f.name)
        if not m:
            continue
        y, z = int(m.group(1)), int(m.group(2))
        temp_f = hwmon / f"pwm{y}_auto_point{z}_temp"
        hyst_f = hwmon / f"pwm{y}_auto_point{z}_temp_hyst"
        try:
            pwm_v = int((read_text(pwm_f) or "0").split()[0])
            # hwmon temp nodes are millidegree Celsius (same convention as
            # temp*_input handled by _temp_c). Expose Celsius like LLT FanTable.
            raw_temp = read_text(temp_f) if temp_f.exists() else None
            raw_hyst = read_text(hyst_f) if hyst_f.exists() else None
            temp_v = round(int(raw_temp.split()[0]) / 1000, 1) if raw_temp else None
            hyst_v = round(int(raw_hyst.split()[0]) / 1000, 1) if raw_hyst else None
        except ValueError:
            continue
        grouped[(y, z)] = {"fan": y, "point": z, "pwm": pwm_v,
                           "pwm_percent": round(pwm_v / 255 * 100),
                           "temp_c": temp_v, "hyst": hyst_v}
    for key in sorted(grouped):
        points.append(grouped[key])
    return {"available": bool(points), "points": points[:40], "hwmon": str(hwmon)}


def set_fan_point(fan: int, point: int, pwm: int | None = None, temp: int | None = None) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked
    hwmon = _legion_hwmon()
    if hwmon is None:
        return {"status": "error", "message": "Fan curve needs the legion-laptop module"}
    try:
        fan_i, point_i = int(fan), int(point)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid fan/point"}
    results = []
    if pwm is not None:
        try:
            pwm_i = max(0, min(255, int(pwm)))
        except (ValueError, TypeError):
            return {"status": "error", "message": "Invalid PWM (0–255)"}
        node = hwmon / f"pwm{fan_i}_auto_point{point_i}_pwm"
        if not node.exists():
            return {"status": "error", "message": f"Point {point_i} for fan {fan_i} not exposed"}
        r = safe_write(node, str(pwm_i))
        results.append(r.get("status") == "success")
        if r.get("status") != "success":
            return {"status": "error", "message": f"Failed to write fan {fan_i} point {point_i} PWM"}
    if temp is not None:
        try:
            temp_c = max(20, min(120, int(temp)))
        except (ValueError, TypeError):
            return {"status": "error", "message": "Invalid temp (20–120°C)"}
        node = hwmon / f"pwm{fan_i}_auto_point{point_i}_temp"
        if not node.exists():
            return {"status": "error", "message": f"Point {point_i} temp not exposed"}
        # Driver expects millidegree; API takes Celsius (see get_fan_curve).
        r = safe_write(node, str(temp_c * 1000))
        results.append(r.get("status") == "success")
        if r.get("status") != "success":
            return {"status": "error", "message": f"Failed to write fan {fan_i} point {point_i} temp"}
    if not results:
        return {"status": "error", "message": "Nothing to set (pass pwm and/or temp)"}
    return {"status": "success", "fan": fan_i, "point": point_i, "pwm": pwm, "temp": temp}


def get_thermals() -> dict:
    temps = {
        "cpu_package": None,
        "cpu_max_core": None,
        "gpu_temp": None,
        "nvme_temp": None,
        "memory_temp": None,
        "pch_temp": None,
        "battery_temp_c": None,
    }

    coretemp = _hwmon_named("coretemp")
    if coretemp:
        hottest = None
        try:
            files = sorted(coretemp.glob("temp*_input"))
        except OSError:
            files = []
        for f in files:
            t = _temp_c(f)
            if t is None:
                continue
            label = read_text(coretemp / f.name.replace("_input", "_label")) or f.stem
            if "package" in label.lower() or "tdie" in label.lower():
                temps["cpu_package"] = t
            hottest = t if hottest is None else max(hottest, t)
        if temps["cpu_package"] is None:
            temps["cpu_package"] = hottest
        temps["cpu_max_core"] = hottest

    # legion_hwmon temps (CPU/GPU/IC for fan control)
    legion = _legion_hwmon()
    if legion is not None:
        for idx, key in ((1, "cpu_package"), (2, "gpu_temp"), (3, "pch_temp")):
            if temps.get(key) is None:
                t = _temp_c(legion / f"temp{idx}_input")
                if t is not None and t > 0:
                    temps[key] = t

    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        name = read_text(hwmon / "name") or ""
        if name == "nvme" and temps["nvme_temp"] is None:
            temps["nvme_temp"] = _temp_c(hwmon / "temp1_input")
        if name == "spd5118":
            t = _temp_c(hwmon / "temp1_input")
            if t is not None:
                temps["memory_temp"] = max(temps["memory_temp"] or 0, t)
        if name in ("pch_cannonlake", "pch_cometlake", "pch_alderlake") and temps["pch_temp"] is None:
            t = _temp_c(hwmon / "temp1_input")
            if t is not None:
                temps["pch_temp"] = t

    # Battery temp (tenths °C in power_supply)
    try:
        for bat in sorted(Path("/sys/class/power_supply").glob("BAT*")):
            raw = read_text(bat / "temp")
            if raw and raw.lstrip("-").isdigit():
                temps["battery_temp_c"] = round(int(raw) / 10, 1)
                break
    except OSError:
        pass

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
