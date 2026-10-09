from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9._+-]+$")

HELPER = Path("/usr/local/bin/omalegion-write")

_helper_ok: bool | None = None


def helper_available() -> bool:
    global _helper_ok
    if _helper_ok is None:
        _helper_ok = HELPER.is_file() and run_cmd(
            ["sudo", "-n", str(HELPER), "--check"], timeout=5.0
        ) is not None
    return bool(_helper_ok)


def read_text(path: Path | str) -> str | None:
    try:
        p = Path(path)
        if p.is_file():
            return p.read_text().strip()
    except OSError:
        pass
    return None


def read_int(path: Path | str) -> int | None:
    raw = read_text(path)
    if raw is None:
        return None
    try:
        return int(raw.split()[0], 0)
    except (ValueError, IndexError):
        return None


def write_direct(path: Path, value: str) -> bool:
    try:
        if path.is_file():
            path.write_text(str(value))
            return True
    except OSError:
        pass
    return False


def write_pkexec(path: Path, value: str) -> tuple[bool, str]:
    if not str(path).startswith("/sys/") or not _SAFE_VALUE.match(str(value)):
        return False, "refused"
    try:
        result = subprocess.run(
            ["pkexec", "tee", str(path)],
            input=str(value) + "\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
        err = (result.stderr or "").strip().splitlines()
        detail = err[-1].split(":", 1)[-1].strip() if err else ""
        return result.returncode == 0, detail
    except (OSError, subprocess.TimeoutExpired):
        return False, "timeout"


def _sudo_run(args: list[str], timeout: float = 15.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["sudo", "-n", str(HELPER)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, ""
        err = (result.stderr or "").strip().splitlines()
        detail = err[-1].split(":")[-1].strip() if err else ""
        return False, detail
    except (OSError, subprocess.TimeoutExpired):
        return False, "timeout"


def write_sudo(path: Path, value: str) -> tuple[bool, str]:
    if not helper_available():
        return False, ""
    return _sudo_run(["write", str(path), str(value)])


def write_many_sudo(pairs: list[tuple[str, str]]) -> tuple[bool, str]:
    if not helper_available():
        return False, ""
    args = ["write-pairs"]
    for path, value in pairs:
        args.extend([str(path), str(value)])
    return _sudo_run(args)


def write_efivar_sudo(path: Path, data: bytes) -> tuple[bool, str]:
    if not helper_available():
        return False, ""
    return _sudo_run(["efivar", str(path), data.hex()], timeout=30.0)


def safe_write(path: Path | str, value: str) -> dict:
    p = Path(path)
    if write_direct(p, value):
        return {"status": "success", "method": "direct"}
    ok, detail = write_sudo(p, value)
    if ok:
        return {"status": "success", "method": "sudo"}
    pk_ok, pk_detail = write_pkexec(p, value)
    if pk_ok:
        return {"status": "success", "method": "pkexec"}
    message = f"Failed to write {value} to {p}"
    reason = detail or pk_detail
    if reason:
        message += f" ({reason})"
    result = {"status": "error", "message": message}
    if reason:
        result["reason"] = reason
    return result


def write_bytes_direct(path: Path, data: bytes) -> bool:
    try:
        if path.is_file() or path.exists():
            path.write_bytes(data)
            return True
    except OSError:
        pass
    return False


def write_bytes_pkexec(path: Path, data: bytes) -> bool:
    try:
        result = subprocess.run(
            ["pkexec", "python3", "-c",
             "import sys; open(sys.argv[1], 'wb').write(bytes.fromhex(sys.argv[2]))",
             str(path), data.hex()],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def safe_write_bytes(path: Path | str, data: bytes) -> dict:
    p = Path(path)
    if write_bytes_direct(p, data):
        return {"status": "success", "method": "direct"}
    ok, detail = write_efivar_sudo(p, data)
    if ok:
        return {"status": "success", "method": "sudo"}
    if write_bytes_pkexec(p, data):
        return {"status": "success", "method": "pkexec"}
    return {"status": "error", "message": f"Failed to write {len(data)} bytes to {p}"}


def install_privileged() -> dict:
    import getpass

    try:
        user = getpass.getuser()
    except OSError:
        return {"status": "error", "message": "Could not determine username"}
    script = Path(__file__).resolve().parent.parent / "install-privilege.sh"
    if not script.is_file():
        return {"status": "error", "message": "Installer script is missing"}
    try:
        result = subprocess.run(
            ["pkexec", "bash", str(script), user],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "error", "message": "Privilege setup timed out"}
    if result.returncode != 0:
        err = (result.stderr or "").strip().splitlines()
        return {"status": "error", "message": err[-1] if err else "Privilege setup failed"}
    global _helper_ok
    _helper_ok = None
    if helper_available():
        return {"status": "success", "message": "Passwordless hardware control enabled"}
    return {"status": "error", "message": "Setup ran but the helper is not active yet"}


def ideapad_dir() -> Path:
    fixed = Path("/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00")
    if fixed.exists():
        return fixed
    try:
        found = sorted(Path("/sys/bus/platform/drivers/ideapad_acpi").glob("VPC*"))
    except OSError:
        found = []
    if found:
        return found[0]
    return fixed


def first_existing(*paths: Path | str) -> Path | None:
    for raw in paths:
        p = Path(raw)
        if p.exists():
            return p
    return None


def run_cmd(args: list[str], timeout: float = 2.0) -> str | None:
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if res.returncode == 0:
            return res.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None
