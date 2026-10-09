from __future__ import annotations

from . import keyboard_rgb


def get_lighting() -> dict:
    keyboard = keyboard_rgb.get_state()
    return {
        "available": keyboard.get("available", False),
        "keyboard": keyboard,
    }


def set_keyboard_power(on: bool) -> dict:
    return keyboard_rgb.set_power(on)


def set_keyboard_effect(effect: str, color: str | None = None, speed: int | None = None, direction: int | None = None) -> dict:
    return keyboard_rgb.set_effect(effect, color, speed, direction)


def set_keyboard_keys(keycodes: list[int], color: str) -> dict:
    return keyboard_rgb.set_keys(keycodes, color)


def set_keyboard_param(speed: int | None = None, direction: int | None = None) -> dict:
    return keyboard_rgb.apply_last(speed, direction)


def set_keyboard_brightness(level: int) -> dict:
    return keyboard_rgb.set_brightness(level)


def set_keyboard_profile(profile: int) -> dict:
    return keyboard_rgb.set_profile(profile)
