from __future__ import annotations

import re
from pathlib import Path

MACHINE_TYPES = {
    "83F0": "legion-5", "83F1": "legion-5", "83M0": "legion-5",
    "83NX": "legion-5", "83N2": "legion-5", "83LY": "legion-5",
    "83DG": "legion-5", "83EW": "legion-5", "83EG": "legion-5",
    "83JJ": "legion-5", "82RC": "legion-5", "82RB": "legion-5",
    "82TB": "legion-5", "83EF": "legion-5", "82RE": "legion-5",
    "83RD": "legion-5", "83Q7": "legion-5", "83Q6": "legion-5",
    "83RW": "legion-5", "83VK": "legion-5",
    "83DH": "legion-slim-5", "83EX": "legion-slim-5", "82Y5": "legion-slim-5",
    "82Y9": "legion-slim-5", "82YA": "legion-slim-5", "83D6": "legion-slim-5",
    "83LT": "legion-pro-5", "83F3": "legion-pro-5", "83DF": "legion-pro-5",
    "83F2": "legion-pro-5", "83LU": "legion-pro-5", "82WM": "legion-pro-5",
    "83NN": "legion-pro-5", "82WK": "legion-pro-5", "82JQ": "legion-pro-5",
    "83KY": "legion-7", "83FD": "legion-7", "82UH": "legion-7",
    "82TD": "legion-7", "82N6": "legion-7",
    "83RU": "legion-pro-7", "83F5": "legion-pro-7", "83DE": "legion-pro-7",
    "82WR": "legion-pro-7", "82WQ": "legion-pro-7", "82WS": "legion-pro-7",
    "83G0": "legion-9", "83EY": "legion-9",
    "83E1": "legion-go",
}

MODEL_KEYWORDS = (
    ("loq", "loq"),
    ("ideapad gaming", "ideapad-gaming"),
    ("ideapad", "ideapad"),
    ("xiaoxin", "ideapad"),
    ("yoga", "yoga"),
    ("lenovo slim", "lenovo-slim"),
    ("thinkbook", "thinkbook"),
    ("legion", "legion-legacy"),
)

KEYBOARD_24ZONE_TYPES = {
    "83F2", "83LT", "83F3", "83F0", "83LY", "83M0", "83F1", "83NX", "83N2",
}


def read(node: str) -> str | None:
    try:
        text = (Path("/sys/class/dmi/id") / node).read_text().strip()
        return text or None
    except OSError:
        return None


def machine_type() -> str | None:
    sku = read("product_sku") or ""
    match = re.search(r"\b([0-9A-Z]{4})\b", sku)
    if match:
        return match.group(1).upper()
    product = read("product_name") or ""
    match = re.search(r"\b([0-9A-Z]{4})\b", product)
    return match.group(1).upper() if match else None


def series(model: str | None, mtm: str | None) -> str:
    if mtm and mtm in MACHINE_TYPES:
        return MACHINE_TYPES[mtm]
    low = (model or "").lower()
    for keyword, name in MODEL_KEYWORDS:
        if keyword in low:
            return name
    return "unknown"


def generation(model: str | None) -> int:
    model = model or ""
    match = re.search(r"(?<=[A-Z]{3})(\d{1,2})", model, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"g(\d+)", model, re.IGNORECASE)
    if match:
        return int(match.group(1))
    for match in re.finditer(r"(?<!\d)\d{1,2}(?!\d)", model):
        value = int(match.group(0))
        if 14 <= value <= 18:
            continue
        return value
    return 0


def keyboard_pid_family(mtm_series: str, gen: int) -> int:
    # Matches LLT Devices.GetKeyboardConfig (Devices.cs): mask 0xFF00 over
    # VID 0x048D; type is C100 / C600 / C900 only.
    if mtm_series == "legion-5" and gen == 11:
        return 0xC600
    if mtm_series == "loq" and gen >= 10:
        return 0xC600
    if mtm_series in ("legion-5", "legion-pro-5", "legion-pro-7", "legion-7") and gen >= 10:
        return 0xC100
    return 0xC900


def get_machine() -> dict:
    vendor = read("sys_vendor")
    product = read("product_name")
    family = read("product_family")
    mtm = machine_type()
    series_name = series(product or family, mtm)
    gen = generation(family or product or "")
    return {
        "vendor": vendor,
        "product": product,
        "family": family,
        "board": read("board_name"),
        "bios_version": read("bios_version"),
        "bios_date": read("bios_date"),
        "machine_type": mtm,
        "series": series_name,
        "generation": gen,
        "keyboard_24zone": mtm in KEYBOARD_24ZONE_TYPES,
    }
