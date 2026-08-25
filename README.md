# Legion Toolkit

An [Omarchy](https://omarchy.org/) bar widget that adds a Lenovo Legion control
center to the shell. Click the bar icon to open a panel with power, GPU,
battery, and cooling controls synced with your laptop firmware and Omarchy's
battery profile.

License: [MIT](LICENSE).

## Features

### Bar widget

- Compact Legion icon on the bar with live tooltip (power mode, battery
  profile, CPU temperature).
- Icon color reflects power mode and thermal state.
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

## Requirements

- Omarchy 4 (Quattro) or newer with the current shell plugin API.
- A Lenovo Legion laptop with Linux sysfs support (`lenovo-wmi-gamezone` or
  equivalent `platform_profile` interface).
- `python3` on `PATH` (used by the bundled hardware engine).
- `pkexec` (PolicyKit) for sysfs writes when direct writes are not permitted.

Optional:

- [`legion-laptop`](https://github.com/johnfanv2/Legion-Laptop) kernel module
  for full PWM fan curves. Without it, fan RPM is read-only on many kernels.

This plugin is Linux- and Omarchy-specific. It depends on Omarchy's
`qs.Commons` and `qs.Ui` components and cannot be used unchanged in an
unrelated Quickshell setup.

## Installation

Replace the repository URL below with your public GitHub URL once the repo is
published.

```bash
omarchy plugin add https://github.com/tedwester/omalegion.git --enable --yes
```

Omarchy clones the repository into:

```text
~/.config/omarchy/plugins/tedwester.legion/
```

### Manual installation

Copy the complete plugin directory to:

```text
~/.config/omarchy/plugins/tedwester.legion/
```

Then rescan and enable:

```bash
omarchy-shell shell rescanPlugins
omarchy plugin enable tedwester.legion
```

Verify:

```bash
omarchy-shell shell listPlugins
omarchy plugin validate ~/.config/omarchy/plugins/tedwester.legion
```

The widget defaults to the right bar section. Add or move it in
`~/.config/omarchy/shell.json`, or run:

```bash
omarchy bar move tedwester.legion --section right
```

## Usage

- Click the Legion icon on the bar to open or close the panel.
- Switch tabs: Overview, Power, GPU, Battery, Cooling.
- Changes that write to sysfs may prompt for your password via PolicyKit.
- Press `Escape` to close the panel.

## Uninstalling

```bash
omarchy plugin remove tedwester.legion --yes
```

This disables the plugin and removes it from the shell. The plugin also stores
rolling thermal history at:

```text
~/.config/omarchy/legion_history.json
```

Delete that file manually if you no longer want the history data.

## What the plugin writes

- Sysfs nodes under `/sys/` (power profile, GPU mode, battery settings, fan
  controls) only when you change a setting in the panel.
- `~/.config/omarchy/legion_history.json` for short in-panel temperature and
  fan charts.

Enabling or disabling the plugin does not modify your bar layout beyond what
Omarchy's plugin enable flow already manages.

## Development

Validate the manifest and entry points before publishing:

```bash
omarchy plugin validate .
```

## Publishing

To list this plugin on [omarchyplugins.com](https://omarchyplugins.com/index.html):

1. Push this repository to a **public** GitHub repo.
2. Ensure `manifest.json`, `README.md`, and `LICENSE` are at the repository
   root.
3. Submit via the [publish form](https://omarchyplugins.com/publish.html).
