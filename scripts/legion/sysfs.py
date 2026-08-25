"""Safe sysfs helpers. Never write outside /sys."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9._+-]+$")


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


def write_pkexec(path: Path, value: str) -> bool:
    if not str(path).startswith("/sys/") or not _SAFE_VALUE.match(str(value)):
        return False
    try:
        result = subprocess.run(
            ["pkexec", "tee", str(path)],
            input=str(value) + "\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def safe_write(path: Path | str, value: str) -> dict:
    p = Path(path)
    if write_direct(p, value):
        return {"status": "success", "method": "direct"}
    if write_pkexec(p, value):
        return {"status": "success", "method": "pkexec"}
    return {"status": "error", "message": f"Failed to write {value} to {p}"}


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
