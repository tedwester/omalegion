from __future__ import annotations

import time
from pathlib import Path

from . import state as plugin_state
from .gpu import dgpu_asleep
from .power import is_custom_mode
from .sysfs import helper_available, read_text, run_cmd, safe_write, write_many_sudo

LEGION_LEVELS = [0, 25, 51, 76, 102, 127, 153, 178, 204, 229, 255]
LEGION_POINTS = 10
LEGION_P10_MIN = 115
LEGION_FULLSPEED = Path("/sys/devices/platform/legion/fan_fullspeed")
LEGION_RPM_TABLE = Path("/sys/devices/platform/legion/fan1_level_rpm_table")


def _legion_hwmon() -> Path | None:
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        if read_text(hwmon / "name") == "legion_hwmon":
            return hwmon
    return None


def _legion_curve(hwmon: Path) -> list[int] | None:
    points = []
    for i in range(1, LEGION_POINTS + 1):
        raw = read_text(hwmon / f"pwm1_auto_point{i}_pwm")
        if raw is None or not raw.lstrip("-").isdigit():
            return None
        points.append(int(raw))
    return points


def _legion_flat_curve(percent: int) -> list[int]:
    base = LEGION_LEVELS[min(10, max(0, round(percent / 10)))]
    points = [base] * LEGION_POINTS
    if points[-1] < LEGION_P10_MIN:
        points[-1] = 127
    return points


def _legion_rpm_table() -> list[int]:
    raw = read_text(LEGION_RPM_TABLE)
    if raw:
        try:
            values = [int(x) for x in raw.split()]
            if len(values) >= 10:
                return values[:10]
        except ValueError:
            pass
    return [0, 1700, 1800, 2000, 2400, 2900, 3700, 4200, 4400, 5500]


def _legion_level(pwm: int) -> int:
    return min(10, max(0, round(pwm / 255 * 10)))


def get_fan_curve() -> dict:
    hwmon = _legion_hwmon()
    if hwmon is None:
        return {"available": False, "points": []}
    raw = _legion_curve(hwmon)
    if raw is None:
        return {"available": False, "points": []}
    table = _legion_rpm_table()
    points = []
    for i, pwm in enumerate(raw, start=1):
        level = _legion_level(pwm)
        points.append({"index": i, "pwm": pwm, "level": level,
                       "rpm": table[level] if 0 <= level < len(table) else None})
    return {"available": True, "points": points}


def set_fan_point(index: int, level: int) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked
    if not 1 <= int(index) <= LEGION_POINTS:
        return {"status": "error", "message": "Fan point out of range"}
    level = max(0, min(10, int(level)))
    hwmon = _legion_hwmon()
    if hwmon is None or _legion_curve(hwmon) is None:
        return {"status": "error", "message": "Manual fan control needs the legion-laptop module"}
    st = plugin_state.load()
    if st.get("fan_curve_default") is None:
        current = _legion_curve(hwmon)
        if current is None:
            return {"status": "error", "message": "Could not read fan curve"}
        st["fan_curve_default"] = current
    pwm = LEGION_LEVELS[level]
    if index == LEGION_POINTS and pwm < LEGION_P10_MIN:
        pwm = 127
    result = safe_write(hwmon / f"pwm1_auto_point{index}_pwm", str(pwm))
    if result["status"] != "success" and result.get("reason") == "Device or resource busy":
        time.sleep(0.6)
        result = safe_write(hwmon / f"pwm1_auto_point{index}_pwm", str(pwm))
    if result["status"] != "success":
        return {"status": "error", "message": "Failed to set fan curve point"}
    st["fan_manual"] = True
    st["fan_percent"] = None
    plugin_state.save(st)
    return {"status": "success", "point": index, "level": level}


def _legion_write_curve(hwmon: Path, points: list[int]) -> bool:
    pairs = [(str(hwmon / f"pwm1_auto_point{i}_pwm"), str(value)) for i, value in enumerate(points, start=1)]
    if helper_available():
        ok, _ = write_many_sudo(pairs)
        return ok
    for path, value in pairs:
        result = safe_write(path, value)
        if result["status"] != "success":
            return False
    return True


def _legion_fans(hwmon: Path) -> list[dict]:
    fans = []
    st = plugin_state.load()
    manual = bool(st.get("fan_manual"))
    for index in (1, 2):
        fan_input = hwmon / f"fan{index}_input"
        if not fan_input.exists():
            continue
        rpm_raw = read_text(fan_input)
        fans.append({
            "index": index,
            "rpm": int(rpm_raw) if rpm_raw and rpm_raw.isdigit() else None,
            "pwm_percent": None,
            "mode": "manual" if manual else "auto",
            "has_control": True,
            "hwmon_name": "legion",
            "hwmon_path": str(hwmon),
            "label": f"Legion fan {index}",
        })
    return fans


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
    legion = _legion_hwmon()
    if legion is not None and _legion_curve(legion) is not None:
        fans.extend(_legion_fans(legion))
        seen.update((f["hwmon_path"], f["index"]) for f in fans)
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


def get_fullspeed() -> dict:
    if not LEGION_FULLSPEED.exists():
        return {"available": False, "enabled": False}
    return {"available": True, "enabled": read_text(LEGION_FULLSPEED) == "1"}


def set_fullspeed(enabled: bool) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked
    if not LEGION_FULLSPEED.exists():
        return {"status": "error", "message": "Full-speed fans need the legion-laptop module"}
    result = safe_write(LEGION_FULLSPEED, "1" if enabled else "0")
    if result["status"] == "success":
        result["fullspeed"] = bool(enabled)
        result["message"] = "Full-speed fans on" if enabled else "Full-speed fans off"
    return result


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
            "manual_available": False,
            "manual_percent": None,
            "fullspeed": get_fullspeed(),
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
        "manual_percent": plugin_state.load().get("fan_percent"),
        "fullspeed": get_fullspeed(),
        "curve": get_fan_curve(),
    }


def set_fan_mode(auto: bool, fan_index: int | None = None) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked

    legion = _legion_hwmon()
    if legion is not None and _legion_curve(legion) is not None:
        st = plugin_state.load()
        if auto:
            saved = st.get("fan_curve_default")
            if isinstance(saved, list) and len(saved) == LEGION_POINTS:
                if not _legion_write_curve(legion, [int(v) for v in saved]):
                    return {"status": "error", "message": "Failed to restore fan curve"}
            st["fan_manual"] = False
            st["fan_percent"] = None
            plugin_state.save(st)
            return {"status": "success", "mode": "auto"}
        st["fan_manual"] = True
        plugin_state.save(st)
        return {"status": "success", "mode": "manual"}

    info = get_fans()
    if not info.get("has_control"):
        return {"status": "error", "message": "Manual fan control needs the legion-laptop module"}

    index = fan_index or info.get("fan_index") or 1
    path = Path(info["hwmon_path"]) / f"pwm{index}_enable"
    result = safe_write(path, "2" if auto else "1")
    if result["status"] == "success":
        result["mode"] = "auto" if auto else "manual"
        st = plugin_state.load()
        st["fan_manual"] = not auto
        st["fan_percent"] = None if auto else st.get("fan_percent")
        plugin_state.save(st)
    return result


def set_fan_speed(percent: int, fan_index: int | None = None) -> dict:
    blocked = _custom_mode_required()
    if blocked:
        return blocked

    legion = _legion_hwmon()
    if legion is not None:
        current = _legion_curve(legion)
        if current is None:
            return {"status": "error", "message": "Legion fan curve is not available"}
        percent = max(0, min(100, int(percent)))
        st = plugin_state.load()
        if st.get("fan_curve_default") is None:
            st["fan_curve_default"] = current
        if not _legion_write_curve(legion, _legion_flat_curve(percent)):
            return {"status": "error", "message": "Failed to set fan speed"}
        st["fan_manual"] = True
        st["fan_percent"] = percent
        plugin_state.save(st)
        return {"status": "success", "percent": percent}

    info = get_fans()
    if not info.get("has_control"):
        return {"status": "error", "message": "Manual fan control needs the legion-laptop module"}

    percent = max(0, min(100, int(percent)))
    index = fan_index or info.get("fan_index") or 1
    base = Path(info["hwmon_path"])
    r1 = safe_write(base / f"pwm{index}_enable", "1")
    r2 = safe_write(base / f"pwm{index}", str(int((percent / 100) * 255)))
    if r1["status"] == "success" and r2["status"] == "success":
        st = plugin_state.load()
        st["fan_manual"] = True
        st["fan_percent"] = percent
        plugin_state.save(st)
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

    if temps["cpu_package"] is None:
        k10temp = _hwmon_named("k10temp")
        if k10temp:
            hottest = None
            for f in sorted(k10temp.glob("temp*_input")):
                t = _temp_c(f)
                if t is None:
                    continue
                label = read_text(k10temp / f.name.replace("_input", "_label")) or f.stem
                if "tdie" in label.lower():
                    temps["cpu_package"] = t
                    break
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

    # Skip nvidia-smi while the dGPU is suspended: probing wakes it and
    # thermal polling alone would keep it awake (see gpu.dgpu_asleep).
    if not dgpu_asleep():
        gpu_out = run_cmd(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            timeout=1.5,
        )
    else:
        gpu_out = None
    if gpu_out:
        try:
            temps["gpu_temp"] = float(gpu_out.splitlines()[0].strip())
        except ValueError:
            pass

    return temps
