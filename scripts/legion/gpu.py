"""GPU working mode, discrete GPU status, and a simple overclock toggle.

Working mode is inferred from PCI boot_vga + driver bind — the same Hybrid vs
dGPU split LLT exposes. Mux changes on this kernel are BIOS/firmware; we do
not write EFI variables. Deactivate uses process termination then runtime PM.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import state as plugin_state
from .sysfs import read_text, run_cmd, safe_write

NVIDIA_PCI = Path("/sys/bus/pci/devices/0000:01:00.0")
INTEL_PCI = Path("/sys/bus/pci/devices/0000:00:02.0")

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


def _find_nvidia_pci() -> Path | None:
    if NVIDIA_PCI.exists():
        return NVIDIA_PCI
    for dev in Path("/sys/bus/pci/devices").glob("*"):
        cls = read_text(dev / "class")
        if cls and cls.startswith("0x0300") and "nvidia" in (read_text(dev / "vendor") or "").lower():
            return dev
        name = run_cmd(["lspci", "-s", dev.name], timeout=1.0) or ""
        if "VGA" in name and "NVIDIA" in name.upper():
            return dev
    return None


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


def _external_nvidia_displays() -> bool:
    for conn in Path("/sys/class/drm").glob("card*-*/status"):
        if read_text(conn) == "connected":
            card = conn.parent.parent.name
            if "nvidia" in card.lower() or "NVIDIA" in card:
                return True
            dev = conn.parent.name
            if dev.startswith("card") and "-" in dev:
                pci_slot = dev.split("-", 1)[1]
                pci_path = Path(f"/sys/class/drm/{dev}/device")
                if pci_path.exists():
                    vendor = read_text(pci_path / "vendor")
                    if vendor and "10de" in vendor.lower():
                        return True
    return False


def _detect_working_mode(nvidia: Path | None) -> str:
    intel_boot = read_text(INTEL_PCI / "boot_vga") == "1" if INTEL_PCI.exists() else False
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
    smi = _nvidia_smi_query()
    powered = bool(smi) or runtime == "active"
    working = _detect_working_mode(nvidia)
    st = plugin_state.load()
    procs = _nvidia_processes() if smi or powered else []
    external = _external_nvidia_displays()

    name = (smi or {}).get("name") or (_lspci_name(nvidia) if nvidia else None) or "NVIDIA GPU"
    intel_name = _lspci_name(INTEL_PCI) or "Intel Graphics"

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
        "working_label": next((m["label"] for m in WORKING_MODES if m["id"] == working), working),
        "working_modes": modes,
        "working_note": "Mux changes need a BIOS reboot on this kernel. Detection stays live.",
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
