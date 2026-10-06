"""Static machine identity."""

from __future__ import annotations

import os
from pathlib import Path

from .sysfs import read_text


def get_system() -> dict:
    info = {
        "product": "Lenovo",
        "family": "Legion",
        "cpu_model": "Unknown CPU",
        "hostname": os.uname().nodename,
        "kernel": os.uname().release,
        "ram_gb": None,
    }
    for key, node in (
        ("vendor", "sys_vendor"),
        ("product", "product_name"),
        ("model", "product_version"),
        ("family", "product_family"),
        ("board", "board_name"),
        ("bios", "bios_version"),
    ):
        val = read_text(Path(f"/sys/class/dmi/id/{node}"))
        if val:
            info[key] = val
    try:
        from .capabilities import get_generation, get_series, is_legion_series

        model = info.get("model") or info.get("product") or ""
        mtm = info.get("product") or ""
        # product holds MTM when model holds marketing name; handle swap.
        if len(str(mtm)) > 6 and not str(model).strip():
            model = mtm
        info["machine_type"] = mtm if len(str(mtm)) <= 6 else ""
        info["series"] = get_series(str(model), str(info.get("machine_type") or ""))
        info["generation"] = get_generation(str(model))
        info["is_legion"] = is_legion_series(info["series"])
    except Exception:
        pass

    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    info["cpu_model"] = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass

    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal"):
                    info["ram_gb"] = round(int(line.split()[1]) / 1_048_576)
                    break
    except (OSError, ValueError):
        pass

    return info
