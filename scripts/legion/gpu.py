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
    pci_root = Path("/sys/bus/pci/devices")
    if pci_root.exists():
        for dev in sorted(pci_root.glob("*")):
            vendor = (read_text(dev / "vendor") or "").strip().lower()
            if vendor == "0x10de":
                return dev
        for dev in sorted(pci_root.glob("*")):
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


def _boot_vga_devices() -> list[Path]:
    """All PCI devices with boot_vga==1 (works for Intel and AMD iGPUs)."""
    boot = []
    root = Path("/sys/bus/pci/devices")
    if not root.exists():
        return boot
    try:
        for dev in sorted(root.glob("*")):
            if read_text(dev / "boot_vga") == "1":
                boot.append(dev)
    except OSError:
        pass
    return boot


def _detect_working_mode(nvidia: Path | None) -> str:
    nvidia_present = nvidia is not None and nvidia.exists()
    nvidia_boot = read_text(nvidia / "boot_vga") == "1" if nvidia_present else False
    nvidia_bound = (nvidia / "driver").exists() if nvidia_present else False
    boot_devs = _boot_vga_devices()
    other_boot = any(dev.name != nvidia.name for dev in boot_devs) if nvidia_present else bool(boot_devs)

    if nvidia_boot and nvidia_present:
        return "dgpu"
    if other_boot and nvidia_present and nvidia_bound:
        return "hybrid"
    if other_boot and not nvidia_present:
        return "igpu"
    if other_boot and nvidia_present and not nvidia_bound:
        # dGPU present but unbound (vfio-pci / driver missing): the panel runs
        # on the other GPU, but the dGPU still exists — report hybrid so the
        # device isn't hidden. LLT would show the mux state instead.
        return "hybrid"
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
    igpu_name = "Integrated Graphics"
    for dev in _boot_vga_devices():
        if nvidia is None or dev.name != nvidia.name:
            igpu_name = _lspci_name(dev) or "Integrated Graphics"
            break
    if igpu_name == "Integrated Graphics" and INTEL_PCI.exists():
        igpu_name = _lspci_name(INTEL_PCI) or igpu_name

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

    live_core, live_mem = (None, None)
    if smi and _oc_backend() == "nvidia-settings":
        try:
            live_core, live_mem = _query_oc_offsets()
        except Exception:
            pass
    stored_core = int(st.get("gpu_core_delta") or 0)
    stored_mem = int(st.get("gpu_mem_delta") or 0)
    oc_enabled = bool(st.get("gpu_oc_enabled") or st.get("gpu_oc"))

    return {
        "available": nvidia is not None and nvidia.exists(),
        "name": name,
        "igpu_name": igpu_name,
        "working_mode": working,
        "working_label": next((m["label"] for m in WORKING_MODES if m["id"] == working), working),
        "working_modes": modes,
        "working_note": "Mux changes need a BIOS reboot on this kernel. Detection stays live. LLT GSync/UMA live-switch needs EnergyDrv.",
        "status": status,
        "powered": powered,
        "runtime": runtime,
        "power_state": power_state,
        "external_display": external,
        "can_deactivate": can_deactivate,
        "can_restart": bool(nvidia and nvidia.exists() and not external and not procs),
        "can_kill_processes": bool(procs),
        "overclock": oc_enabled,
        "overclock_available": bool(smi),
        "overclock_backend": _oc_backend(),
        "overclock_core_delta": live_core if live_core is not None else stored_core,
        "overclock_mem_delta": live_mem if live_mem is not None else stored_mem,
        "overclock_core_min": -500,
        "overclock_core_max": 500,
        "overclock_mem_min": -3000,
        "overclock_mem_max": 3000,
        "overclock_voltage_supported": False,
        "overclock_note": "Core -500…+500 / Mem -3000…+3000 MHz via nvidia-settings (Coolbits 8), like LLT. Voltage V/F curve is NVAPI-only, unsupported on Linux.",
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


def _oc_backend() -> str:
    import shutil

    if shutil.which("nvidia-settings"):
        return "nvidia-settings"
    if shutil.which("nvidia-smi"):
        return "nvidia-smi"
    return "none"


def _query_oc_offsets() -> tuple[int | None, int | None]:
    """Read current offsets via nvidia-settings query. None if unavailable."""
    core = run_cmd(
        ["nvidia-settings", "-t", "-q", "[gpu:0]/GPUGraphicsClockOffsetAllPerformanceLevels"],
        timeout=3.0,
    )
    mem = run_cmd(
        ["nvidia-settings", "-t", "-q", "[gpu:0]/GPUMemoryTransferRateOffsetAllPerformanceLevels"],
        timeout=3.0,
    )

    def parse(v: str | None) -> int | None:
        if not v:
            return None
        # nvidia-settings -t may print "0", "0, 0", or multi-line lists.
        m = re.search(r"-?\d+", v)
        if not m:
            return None
        try:
            return int(m.group(0))
        except ValueError:
            return None

    return parse(core), parse(mem)


def set_gpu_oc_delta(core_delta: int, mem_delta: int) -> dict:
    """LLT-equivalent delta OC. Ranges mirror GPUOverclockController clamps."""
    try:
        core_i, mem_i = int(core_delta), int(mem_delta)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid OC deltas"}
    if not (-500 <= core_i <= 500):
        return {"status": "error", "message": f"Core offset {core_i} out of range -500…+500 MHz (LLT clamp)"}
    if not (-3000 <= mem_i <= 3000):
        return {"status": "error", "message": f"Memory offset {mem_i} out of range -3000…+3000 MHz (LLT clamp)"}
    if not Path("/dev/nvidia0").exists() and not Path("/dev/nvidiactl").exists():
        # Persist for next wake, like LLT SaveState without apply.
        st = plugin_state.load()
        st["gpu_core_delta"] = core_i
        st["gpu_mem_delta"] = mem_i
        st["gpu_oc_enabled"] = core_i != 0 or mem_i != 0
        st["gpu_oc"] = st["gpu_oc_enabled"]
        plugin_state.save(st)
        return {"status": "success", "core_delta": core_i, "mem_delta": mem_i,
                "message": "Saved. Will apply the next time the dGPU wakes."}
    if _oc_backend() != "nvidia-settings":
        return {
            "status": "error",
            "message": "Delta overclock needs nvidia-settings with Coolbits 8 (Option \"Coolbits\" \"8\"). nvidia-smi can only lock clocks, not offset them.",
        }
    import os
    import subprocess

    env = dict(os.environ)
    if not env.get("DISPLAY"):
        env["DISPLAY"] = ":0"
    try:
        r1 = subprocess.run(
            ["nvidia-settings", "-a", f"[gpu:0]/GPUGraphicsClockOffsetAllPerformanceLevels={core_i}"],
            capture_output=True, text=True, timeout=8, env=env,
        )
        r2 = subprocess.run(
            ["nvidia-settings", "-a", f"[gpu:0]/GPUMemoryTransferRateOffsetAllPerformanceLevels={mem_i}"],
            capture_output=True, text=True, timeout=8, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "message": f"nvidia-settings failed: {exc}"}
    if r1.returncode == 0 and r2.returncode == 0:
        st = plugin_state.load()
        st["gpu_core_delta"] = core_i
        st["gpu_mem_delta"] = mem_i
        st["gpu_oc_enabled"] = core_i != 0 or mem_i != 0
        st["gpu_oc"] = st["gpu_oc_enabled"]
        plugin_state.save(st)
        return {"status": "success", "core_delta": core_i, "mem_delta": mem_i,
                "message": f"OC {core_i:+d} MHz core / {mem_i:+d} MHz mem applied"}
    err = (r1.stderr or r2.stderr or "").strip()[:300]
    if "Coolbits" in err or "not supported" in err.lower() or "permission" in err.lower():
        return {"status": "error",
                "message": "nvidia-settings rejected offsets. Enable Coolbits 8 and run from a graphical session. " + err}
    return {"status": "error", "message": f"nvidia-settings failed: {err or 'unknown error'}"}


def set_gpu_oc(enabled: bool) -> dict:
    """Legacy bool toggle: on = re-apply stored deltas, off = reset to 0."""
    st = plugin_state.load()
    if not enabled:
        st["gpu_oc_enabled"] = False
        st["gpu_oc"] = False
        clock_lock = bool(st.pop("gpu_clock_lock", False))
        plugin_state.save(st)
        if _oc_backend() == "nvidia-settings" and (Path("/dev/nvidia0").exists() or Path("/dev/nvidiactl").exists()):
            return set_gpu_oc_delta(0, 0)
        # Only reset clock locks if this plugin applied one. Never touch
        # unrelated -lgc locks (LLT never resets what it didn't set).
        if clock_lock and _oc_backend() == "nvidia-smi":
            run_cmd(["nvidia-smi", "-rgc"], timeout=3.0)
        return {"status": "success", "gpu_oc": False}
    core = int(st.get("gpu_core_delta") or 0)
    mem = int(st.get("gpu_mem_delta") or 0)
    if core == 0 and mem == 0:
        # No deltas stored: fall back to max-clock lock via nvidia-smi so the
        # toggle still does something useful without Coolbits.
        if Path("/dev/nvidia0").exists() or Path("/dev/nvidiactl").exists():
            run_cmd(["nvidia-smi", "-pm", "1"], timeout=3.0)
        st["gpu_oc_enabled"] = True
        st["gpu_oc"] = True
        st["gpu_clock_lock"] = True
        plugin_state.save(st)
        return {"status": "success", "gpu_oc": True,
                "message": "OC enabled (clock-lock fallback — set core/mem offsets for true LLT-style OC)."}
    res = set_gpu_oc_delta(core, mem)
    if res.get("status") == "success":
        st = plugin_state.load()
        st["gpu_oc_enabled"] = True
        st["gpu_oc"] = True
        st.pop("gpu_clock_lock", None)
        plugin_state.save(st)
    return res


def restart_dgpu() -> dict:
    """LLT GPUController.RestartGPUAsync equivalent via PCI remove + rescan.

    Unlike LLT's atomic pnputil restart this is NOT atomic: if rescan fails
    the device stays gone until reboot. Guarded to bound+idle only.
    """
    nvidia = _find_nvidia_pci()
    if not nvidia or not nvidia.exists():
        return {"status": "error", "message": "Discrete GPU not found"}
    if not (nvidia / "driver").exists():
        return {"status": "error", "message": "dGPU has no driver bound — nothing to restart"}
    if _external_nvidia_displays():
        return {"status": "error", "message": "Disconnect external displays on the dGPU first."}
    procs = _nvidia_processes()
    if procs:
        return {"status": "error", "message": f"dGPU in use ({', '.join(p['name'] for p in procs[:4])}). Deactivate first."}
    if (read_text(nvidia / "power/runtime_status") or "") == "suspended":
        return {"status": "error", "message": "dGPU is suspended — wake it (run something on it) before restart"}
    # remove + rescan needs root; safe_write handles pkexec for /sys.
    rm = nvidia / "remove"
    if not rm.exists():
        return {"status": "error", "message": "GPU remove node not exposed on this kernel"}
    addr = nvidia.name
    r = safe_write(rm, "1")
    if r.get("status") != "success":
        return {"status": "error", "message": "Failed to remove dGPU (need root via pkexec)"}
    import time as _time

    _time.sleep(1.0)
    r2 = safe_write(Path("/sys/bus/pci/rescan"), "1")
    if r2.get("status") != "success":
        return {"status": "error", "message": "dGPU removed but rescan failed — reboot may be needed"}
    _time.sleep(1.0)
    if _find_nvidia_pci() is None:
        return {"status": "error", "message": "Rescan finished but dGPU did not re-enumerate — reboot may be needed"}
    return {"status": "success", "message": f"dGPU {addr} restarted (remove + rescan, re-enumerated)"}
