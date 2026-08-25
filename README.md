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
- Fn lock and keyboard backlight controls.

### Power

- Legion thermal modes (Quiet, Balanced, Performance, Extreme, Custom) via
  `platform_profile`, synced with Omarchy's power-profiles-daemon battery
  panel.
- Custom mode PPT (power limit) tuning when supported.

### GPU

- Hybrid / dGPU-only / iGPU-only working modes.
- dGPU deactivate, overclock controls, and active GPU process list.

### Battery

- Charge modes (normal, conservation, rapid charge, overnight).
- Always-on USB charging toggle.

### Cooling

- Fan mode presets and manual fan speed when PWM is available.
- Live thermal sensors and short temperature/fan history charts.

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
