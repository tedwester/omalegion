# Legion Toolkit

An [Omarchy](https://omarchy.org/) bar widget that adds a Lenovo Legion control
center to the shell. Click the bar icon to open a panel with power, GPU,
battery, and cooling controls synced with your laptop firmware and Omarchy's
battery profile.

License: [MIT](LICENSE).

The bar and panel logo is from
[LenovoLegionToolkit](https://github.com/LenovoLegionToolkit-Team/LenovoLegionToolkit)
(`assets/logo.png`).

## Features

### Bar widget

- Compact Legion icon on the bar with live tooltip (power mode, battery
  profile, CPU temperature).
- Icon badge reflects power mode and thermal state (blue = quiet, white =
  balanced, accent = performance, purple = extreme/custom). Optional monochrome
  bar icon in the Misc tab.
- Click to open or close the control panel.

### Overview

- Power mode, CPU/GPU temperatures, fan RPM, battery level, and GPU status at
  a glance.
- Fn lock, keyboard backlight levels (LLT WhiteKeyboard Off/Low/High),
  touchpad, mic/speaker mute.

### Misc (System)

- Display brightness + connected outputs, Y-logo / ports lighting where
  `legion-laptop` exposes them, device capability summary.
- RGB 4-zone / Spectrum / LampArray are HID-proprietary and reported
  unsupported (use OpenRGB where supported) — like LLT hides unsupported
  controllers.
- Monochrome bar icon toggle.
- Plugin version and quick links.

### Power

- Legion thermal modes (Quiet, Balanced, Performance, Extreme, Custom) via
  `platform_profile`, synced with Omarchy's power-profiles-daemon battery
  panel. Extreme/Custom hide when your firmware doesn't expose them (LLT
  `SupportsExtremeMode` / GodMode gating).
- Custom mode (GodMode-lite): all firmware power/temp limits your BIOS
  exposes (`ppt_*`, `cpu/gpu_*`, RAPL fallback), with firmware min/max
  validation, plus named presets (save/apply/delete).

### GPU

- Hybrid / dGPU-only / iGPU-only working modes (detection live, mux switch
  via BIOS like LLT without EnergyDrv).
- dGPU deactivate, restart (PCI remove + rescan, LLT RestartGPU), and active
  GPU process list.
- Delta overclock exactly like LLT clamps (core -500…+500, mem
  -3000…+3000 MHz) via `nvidia-settings` (Coolbits 8). Without it the toggle
  only locks/resets clocks via `nvidia-smi`. Voltage V/F is NVAPI-only and
  reported unsupported.

### Battery

- Charge modes (normal, conservation, rapid charge).
- Always-on USB as LLT 3-state (Off / On-when-sleeping / On-always) where the
  firmware exposes it; ideapad-only machines show Off / On-when-sleeping.
- Overnight hold as software policy (configurable 22:00–07:00 window) with
  explicit tick — reads never write. LLT firmware Night Charge persists
  without OS and is noted as such.
- Extra telemetry (power, temp), Flip To Start via UEFI FBSWIF where present.
  Instant Boot is WMI-only and reported unsupported (switch in BIOS).

### Cooling

- Fan RPM + full sensor set (CPU package/cores, GPU, NVMe, memory, PCH,
  battery temp).
- Manual PWM per fan + fan full-speed toggle (legion-laptop), both requiring
  Custom mode like LLT GodMode.
- 10-point fan-curve readout (`pwmY_auto_pointZ_*`, LLT FanTable
  equivalent) with `--set-fan-point` writes.

### Misc

- Monochrome bar icon toggle.
- Plugin version and quick links.

## Requirements

- Omarchy 4 (Quattro) or newer with the current shell plugin API.
- A Lenovo Legion laptop with Linux sysfs support (`lenovo-wmi-gamezone` or
  equivalent `platform_profile` interface).
- `python3` on `PATH` (used by the bundled hardware engine).
- `pkexec` (PolicyKit) for sysfs writes when direct writes are not permitted.

Optional:

- [`legion-laptop`](https://github.com/johnfanv2/Legion-Laptop) kernel module
  for full PWM fan curves. Without it, fan RPM is read-only on many kernels.

## Installation

```bash
omarchy plugin add https://github.com/tedwester/omalegion.git --enable --yes
```

Omarchy clones the repository into
`~/.config/omarchy/plugins/tedwester.legion/` and enables the widget on the
right bar section by default.

If the icon does not appear after install:

```bash
omarchy bar put tedwester.legion --section right --after omarchy.tray
```

### Manual installation

Copy the complete plugin directory to
`~/.config/omarchy/plugins/tedwester.legion/`, then run:

```bash
omarchy-shell shell rescanPlugins
omarchy plugin enable tedwester.legion --section right
```

## Usage

- Click the Legion icon on the bar to open or close the panel.
- Switch tabs: Overview, Power, GPU, Battery, Cooling, Misc.
- Changes that write to sysfs may prompt for your password via PolicyKit.
- Press `Escape` to close the panel.

## Uninstalling

```bash
omarchy plugin remove tedwester.legion --yes
```

This disables the plugin and removes it from the shell. The plugin also stores
rolling thermal history at `~/.config/omarchy/legion_history.json`. Delete that
file manually if you no longer want the history data.

## What the plugin writes

- Sysfs nodes under `/sys/` (power profile, GPU mode, battery settings, fan
  controls) only when you change a setting in the panel.
- `~/.config/omarchy/legion_history.json` for short in-panel temperature and
  fan charts.
- `~/.config/omarchy/legion_state.json` for a few panel toggles (for example
  GPU overclock and overnight charging).

Enabling or disabling the plugin does not modify your bar layout beyond what
Omarchy's plugin enable flow already manages.
