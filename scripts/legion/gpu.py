from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import state as plugin_state
from .sysfs import read_text, run_cmd, safe_write

NVIDIA_PCI = Path("/sys/bus/pci/devices/0000:01:00.0")
LEGION_IGPUMODE = Path("/sys/devices/platform/legion/igpumode")
LEGION_GSYNC = Path("/sys/devices/platform/legion/gsync")

LEGION_IGPU_MODES = [
    {
        "id": "hybrid",
        "legion": "0",
        "label": "Hybrid",
        "desc": "iGPU drives the panel. dGPU wakes on demand, then powers off.",
    },
    {
        "id": "igpu-only",
        "legion": "1",
        "label": "iGPU only",
        "desc": "dGPU disconnected for best battery. May need a reboot.",
    },
    {
        "id": "hybrid-auto",
        "legion": "2",
        "label": "Hybrid auto",
        "desc": "Firmware connects and disconnects the dGPU automatically.",
    },
]


def _legion_igpu() -> str | None:
    if not LEGION_IGPUMODE.exists():
        return None
    return read_text(LEGION_IGPUMODE)


def get_gsync() -> dict:
    if not LEGION_GSYNC.exists():
        return {"available": False, "enabled": False}
    return {"available": True, "enabled": read_text(LEGION_GSYNC) == "0"}


def set_gsync(enabled: bool) -> dict:
    if not LEGION_GSYNC.exists():
        return {"status": "error", "message": "G-Sync control needs the legion-laptop module"}
    result = safe_write(LEGION_GSYNC, "0" if enabled else "1")
    if result["status"] == "success":
        if read_text(LEGION_GSYNC) != ("0" if enabled else "1"):
            return {"status": "error", "message": "Firmware did not apply the G-Sync change"}
        result["gsync"] = bool(enabled)
        result["message"] = "G-Sync on" if enabled else "G-Sync off"
    return result

WORKING_MODES = [
    {
        "id": "hybrid",
        "label": "Hybrid",
        "desc": "iGPU drives the panel. dGPU wakes on demand, then powers off.",
    },
    {
        "id": "dgpu",
        "label": "Discrete GPU",
        "desc": "Internal display on the NVIDIA GPU. Best performance, worst idle power.",
    },
    {
        "id": "igpu",
        "label": "iGPU only",
        "desc": "dGPU disconnected. Best battery. Set this in BIOS on current kernels.",
    },
]


def _find_pci(vendor_id: str) -> Path | None:
    for dev in sorted(Path("/sys/bus/pci/devices")):
        if (read_text(dev / "class") or "").startswith("0x030") and (read_text(dev / "vendor") or "").lower() == vendor_id:
            return dev
    return None


def _find_nvidia_pci() -> Path | None:
    known = Path("/sys/bus/pci/devices/0000:01:00.0")
    if known.exists():
        return known
    found = _find_pci("0x10de")
    if found:
        return found
    for dev in Path("/sys/bus/pci/devices").glob("*"):
        name = run_cmd(["lspci", "-s", dev.name], timeout=1.0) or ""
        if "VGA" in name and "NVIDIA" in name.upper():
            return dev
    return None


def _find_igpu_pci() -> Path | None:
    known = Path("/sys/bus/pci/devices/0000:00:02.0")
    if known.exists():
        return known
    return _find_pci("0x8086") or _find_pci("0x1022")


def _lspci_name(pci: Path) -> str | None:
    if not pci.exists():
        return None
    addr = pci.name
    out = run_cmd(["lspci", "-s", addr], timeout=1.0)
    if not out:
        return None
    parts = out.split(":", 2)
    if len(parts) >= 3:
        name = parts[2].strip()
        for junk in ("NVIDIA Corporation ", "Intel Corporation ", "[AMD/ATI] "):
            name = name.replace(junk, "")
        name = re.sub(r"\s*\(rev [0-9a-fA-F]+\)", "", name).strip()
        if "[" in name and "]" in name:
            inner = name[name.find("[") + 1 : name.find("]")]
            if inner:
                return inner
        return name.strip()
    return None


def _nvidia_smi_query() -> dict | None:
    if not Path("/dev/nvidia0").exists() and not Path("/dev/nvidiactl").exists():
        return None
    out = run_cmd(
        [
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,"
            "power.draw,power.limit,driver_version,clocks.current.graphics,clocks.current.memory,pstate",
            "--format=csv,noheader,nounits",
        ],
        timeout=2.5,
    )
    if not out:
        return None
    parts = [p.strip() for p in out.split(",")]
    if len(parts) < 8:
        return None

    def num(idx, cast=float):
        try:
            return cast(parts[idx])
        except (ValueError, IndexError):
            return None

    return {
        "name": parts[0],
        "temp": num(1),
        "utilization": num(2, int),
        "memory_used_mb": num(3),
        "memory_total_mb": num(4),
        "power_draw_w": num(5),
        "power_cap_w": num(6),
        "driver": parts[7],
        "clock_core_mhz": num(8, int),
        "clock_memory_mhz": num(9, int) if len(parts) > 9 else None,
        "pstate": parts[10] if len(parts) > 10 else None,
    }


def _nvidia_processes() -> list[dict]:
    out = run_cmd(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"],
        timeout=1.5,
    )
    if not out:
        return []
    procs = []
    for line in out.splitlines():
        bits = [b.strip() for b in line.split(",")]
        if len(bits) >= 2 and bits[0].isdigit():
            procs.append({
                "pid": int(bits[0]),
                "name": Path(bits[1]).name,
                "mem_mb": bits[2] if len(bits) > 2 else "—",
            })
    return procs[:8]


def dgpu_asleep() -> bool:
    """True when runtime PM reports the dGPU suspended (D3cold).

    nvidia-smi wakes a suspended dGPU, so callers must skip nvidia-smi
    probes while this is true or monitoring alone keeps the dGPU awake.
    """
    nvidia = _find_nvidia_pci()
    if not nvidia or not nvidia.exists():
        return True
    return (
        read_text(nvidia / "power/runtime_status") == "suspended"
        or read_text(nvidia / "power_state") == "D3cold"
    )


def _external_nvidia_displays() -> bool:
    for conn in Path("/sys/class/drm").glob("card*-*/status"):
        if read_text(conn) == "connected":
            dev = conn.parent.name
            if dev.startswith("card") and "-" in dev:
                pci_path = Path(f"/sys/class/drm/{dev}/device")
                if pci_path.exists():
                    vendor = read_text(pci_path / "vendor")
                    if vendor and "10de" in vendor.lower():
                        return True
    return False


def _detect_working_mode(nvidia: Path | None) -> str:
    intel = _find_igpu_pci()
    intel_boot = read_text(intel / "boot_vga") == "1" if intel and intel.exists() else False
    nvidia_present = nvidia is not None and nvidia.exists()
    nvidia_boot = read_text(nvidia / "boot_vga") == "1" if nvidia_present else False
    nvidia_bound = (nvidia / "driver").exists() if nvidia_present else False

    if nvidia_boot and nvidia_present:
        return "dgpu"
    if intel_boot and nvidia_present and nvidia_bound:
        return "hybrid"
    if intel_boot and not nvidia_present:
        return "igpu"
    if intel_boot and nvidia_present and not nvidia_bound:
        return "igpu"
    if nvidia_present:
        return "hybrid"
    return "unknown"


def _kill_dgpu_processes(procs: list[dict]) -> list[str]:
    for proc in procs:
        pid = proc.get("pid")
        if not pid:
            continue
        try:
            subprocess.run(["kill", "-TERM", str(pid)], timeout=1.0, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass

    remaining = {p["pid"] for p in _nvidia_processes()}
    failed = []
    for proc in procs:
        pid = proc.get("pid")
        if pid and pid in remaining:
            failed.append(proc.get("name") or str(pid))
    return failed


def get_gpu() -> dict:
    nvidia = _find_nvidia_pci()
    runtime = read_text(nvidia / "power/runtime_status") if nvidia else None
    power_state = read_text(nvidia / "power_state") if nvidia else None
    # Skip nvidia-smi while suspended: probing wakes the dGPU and polling
    # alone would keep it awake (see dgpu_asleep).
    asleep = runtime == "suspended" or power_state == "D3cold"
    smi = None if asleep else _nvidia_smi_query()
    powered = bool(smi) or runtime == "active"
    working = _detect_working_mode(nvidia)
    st = plugin_state.load()
    procs = _nvidia_processes() if smi or powered else []
    external = _external_nvidia_displays()

    name = (smi or {}).get("name") or (_lspci_name(nvidia) if nvidia else None) or "NVIDIA GPU"
    intel = _find_igpu_pci()
    intel_name = (_lspci_name(intel) if intel else None) or "Integrated Graphics"

    status = "Unknown"
    if not nvidia or not nvidia.exists():
        status = "Not found"
    elif runtime == "suspended" or power_state == "D3cold":
        status = "Powered off"
    elif smi and (smi.get("utilization") or 0) > 0:
        status = "Active"
    elif powered:
        status = "Idle"
    else:
        status = "Unavailable"

    modes = []
    legion_igpu = _legion_igpu()
    if legion_igpu is not None:
        current_legion = next((m for m in LEGION_IGPU_MODES if m["legion"] == legion_igpu), None)
        working = current_legion["id"] if current_legion else working
        for mode in LEGION_IGPU_MODES:
            modes.append({**mode, "selected": mode["id"] == working, "switchable": True})
    else:
        for mode in WORKING_MODES:
            modes.append({**mode, "selected": mode["id"] == working, "switchable": False})

    can_deactivate = (
        working == "hybrid"
        and powered
        and status in ("Active", "Idle")
        and not external
    )

    return {
        "available": nvidia is not None and nvidia.exists(),
        "name": name,
        "igpu_name": intel_name,
        "working_mode": working,
        "working_label": next((m["label"] for m in modes if m["id"] == working), working),
        "working_modes": modes,
        "working_note": "Applies immediately. A reboot may be needed on some firmware." if legion_igpu is not None else "Mux changes need a BIOS reboot on this kernel. Detection stays live.",
        "gsync": get_gsync(),
        "status": status,
        "powered": powered,
        "runtime": runtime,
        "power_state": power_state,
        "external_display": external,
        "can_deactivate": can_deactivate,
        "can_kill_processes": bool(procs),
        "overclock": bool(st.get("gpu_oc")),
        "overclock_available": bool(smi),
        "processes": procs,
        "temp": (smi or {}).get("temp"),
        "utilization": (smi or {}).get("utilization"),
        "memory_used_mb": (smi or {}).get("memory_used_mb"),
        "memory_total_mb": (smi or {}).get("memory_total_mb"),
        "power_draw_w": (smi or {}).get("power_draw_w"),
        "power_cap_w": (smi or {}).get("power_cap_w"),
        "driver": (smi or {}).get("driver"),
        "clock_core_mhz": (smi or {}).get("clock_core_mhz"),
        "clock_memory_mhz": (smi or {}).get("clock_memory_mhz"),
        "pstate": (smi or {}).get("pstate"),
    }


def set_gpu_mode(mode: str) -> dict:
    legion_ids = {m["id"]: m["legion"] for m in LEGION_IGPU_MODES}
    if mode in legion_ids and LEGION_IGPUMODE.exists():
        if _external_nvidia_displays() and mode == "igpu-only":
            return {"status": "error", "message": "Disconnect external displays on the dGPU first."}
        if read_text(LEGION_IGPUMODE) == legion_ids[mode]:
            return {"status": "success", "gpu_mode": mode, "message": f"GPU mode: {mode} (already active)"}
        result = safe_write(LEGION_IGPUMODE, legion_ids[mode])
        if result["status"] == "success":
            if read_text(LEGION_IGPUMODE) != legion_ids[mode]:
                return {"status": "error", "message": "Firmware did not apply the GPU mode change"}
            result["gpu_mode"] = mode
            result["message"] = f"GPU mode: {mode}"
        return result
    if mode not in {m["id"] for m in WORKING_MODES}:
        return {"status": "error", "message": f"Unknown GPU mode: {mode}"}
    nvidia = _find_nvidia_pci()
    current = _detect_working_mode(nvidia)
    if mode == current:
        return {"status": "success", "gpu_mode": mode, "message": "Already active"}
    return {
        "status": "error",
        "message": "GPU working mode is firmware-muxed. Switch Hybrid / Discrete in BIOS, then reboot.",
    }


def deactivate_dgpu(kill_processes: bool = False) -> dict:
    nvidia = _find_nvidia_pci()
    if not nvidia or not nvidia.exists():
        return {"status": "error", "message": "Discrete GPU not found"}
    if _detect_working_mode(nvidia) != "hybrid":
        return {"status": "error", "message": "Deactivate dGPU only works in Hybrid mode."}
    if _external_nvidia_displays():
        return {"status": "error", "message": "Disconnect external displays on the dGPU first."}

    procs = _nvidia_processes()
    if procs:
        if not kill_processes:
            names = ", ".join(p["name"] for p in procs[:4])
            return {
                "status": "error",
                "message": f"dGPU is in use ({names}). End those apps or use force deactivate.",
                "processes": procs,
                "can_kill": True,
            }
        failed = _kill_dgpu_processes(procs)
        if failed:
            return {
                "status": "error",
                "message": f"Could not stop: {', '.join(failed)}",
                "processes": _nvidia_processes(),
            }
        procs = _nvidia_processes()
        if procs:
            return {
                "status": "error",
                "message": "Some dGPU processes are still running.",
                "processes": procs,
            }

    control = nvidia / "power" / "control"
    result = safe_write(control, "auto")
    if result["status"] == "success":
        result["dgpu"] = "suspend-requested"
        if kill_processes:
            result["killed_processes"] = True
    return result


def set_gpu_oc(enabled: bool) -> dict:
    st = plugin_state.load()
    st["gpu_oc"] = bool(enabled)
    plugin_state.save(st)

    if not Path("/dev/nvidia0").exists() and not Path("/dev/nvidiactl").exists():
        return {
            "status": "success",
            "gpu_oc": bool(enabled),
            "message": "Saved. Will apply the next time the dGPU wakes.",
        }

    if enabled:
        run_cmd(["nvidia-smi", "-pm", "1"], timeout=3.0)
        out = run_cmd(["nvidia-smi", "--query-supported-clocks=gr", "--format=csv,noheader,nounits"], timeout=2.0)
        if out:
            try:
                mhz = max(int(x.strip()) for x in out.splitlines() if x.strip().isdigit())
                run_cmd(["nvidia-smi", "-lgc", str(mhz)], timeout=3.0)
            except ValueError:
                pass
        return {"status": "success", "gpu_oc": True}

    run_cmd(["nvidia-smi", "-rgc"], timeout=3.0)
    return {"status": "success", "gpu_oc": False}
