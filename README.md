# Legion Toolkit

An [Omarchy](https://omarchy.org/) bar widget that adds a Lenovo Legion control
center to the shell. Click the bar icon to open a panel with overview, power,
GPU, battery, cooling, input, and lighting controls synced with your laptop
firmware and Omarchy's battery profile.

License: [MIT](LICENSE).

The bar and panel logo is from
[LenovoLegionToolkit](https://github.com/LenovoLegionToolkit-Team/LenovoLegionToolkit)
(`assets/logo.png`).

## Features

### Bar widget

- Compact Legion icon on the bar with live tooltip (power mode, battery
  profile, CPU temperature).
- Icon badge reflects the power mode (blue = quiet, white =
  balanced, red = performance, purple = extreme/custom). Optional monochrome
  bar icon in the Misc tab.
- Click to open or close the control panel.

### Overview

- Power mode, CPU/GPU temperatures, fan RPM, battery level, and GPU status at
  a glance.

### Input

- Fn Lock and touchpad on/off. With the `legion-laptop` module the
  touchpad switches in firmware; without it, the toggle applies to the
  Hyprland session instead.
- Microphone and speaker mute, plus speaker volume presets (via PipeWire).
- Flip to Start: boot the laptop by opening the lid (UEFI setting).

Linux does not expose firmware interfaces for the Windows-only Legion
Toolkit features (Instant Boot, ITS thermal modes), so those are not
available here. Every other control checks what your machine supports and
only shows what is available.

### Power

- Legion thermal modes (Quiet, Balanced, Performance, Custom) via
  `platform_profile`, synced with Omarchy's power-profiles-daemon battery
  panel.
- Custom mode PPT (power limit) tuning when supported. Entering Custom mode
  needs the `legion-laptop` kernel module (see Requirements). With the
  module loaded, Extreme is not offered because the module does not expose
  it.

### GPU

- Hybrid / iGPU-only / Hybrid-auto working modes with the `legion-laptop`
  module (detection only without it; switching modes may need a reboot).
- G-Sync status, dGPU deactivate, overclock toggle, and active GPU process
  list.

### Battery

- Charge modes (normal, conservation, rapid charge, overnight).
- Always-on USB charging toggle.

### Cooling

- Silent / Balanced / Maximum fan presets. With the `legion-laptop`
  module they program the firmware fan curve (your previous curve is
  restored when you switch back to Automatic); without it, fans are
  read-only on most kernels.
- Adjustable 10-point fan curve with per-point levels and RPM, same
  model as Legion Toolkit (speeds only; the temperature steps are fixed
  in firmware).
- Full-speed fans toggle (Custom power mode required).
- Live thermal sensors and short temperature/fan history charts.

### Lighting

- Keyboard backlight on Spectrum (per-key hardware) Legion laptops,
  detected automatically per machine with its true key layout read live
  from the device: on/off, brightness, lighting slots (the same slots
  Fn+Space cycles), ten firmware effects with speed and direction,
  static colors, and per-key painting on an annotated layout grid.
  Audio-reactive and screen-capture effects need a live loop and are
  not included.

### Misc

- Monochrome bar icon toggle.
- Passwordless hardware control: one-time setup (one password prompt) that
  installs a restricted sudo rule so every hardware setting applies without
  further prompts. To remove it later, delete `/etc/sudoers.d/omalegion`
  and `/usr/local/bin/omalegion-write`.

## Requirements

- Omarchy 4 (Quattro) or newer with the current shell plugin API.
- A Lenovo Legion laptop with Linux sysfs support (`lenovo-wmi-gamezone` or
  equivalent `platform_profile` interface).
- `python3` on `PATH` (used by the bundled hardware engine).
- `pkexec` (PolicyKit) for system writes when direct writes are not
  permitted, and `sudo` for the optional passwordless setup in Misc.

Optional:

- [`legion-laptop`](https://github.com/johnfanv2/LenovoLegionLinux) kernel
  module for Custom power mode and firmware fan curves. Without it, fan RPM
  is read-only on many kernels and the firmware rejects entering Custom
  mode. On Arch-based systems the panel offers a one-tap installer for the
  `lenovolegionlinux-dkms-git` AUR package wherever the module is needed.

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
- Switch tabs: Overview, Power, GPU, Battery, Cooling, Input, Lighting,
  Misc (`Tab` and `Shift+Tab` cycle through them).
- The panel updates live on audio and power-supply events and re-checks
  sensors every 10 seconds. Press `R` to refresh immediately.
- Without the passwordless setup in Misc, changes that write to system
  settings may prompt for your password via PolicyKit.
- Press `Escape` to close the panel.

## Uninstalling

```bash
omarchy plugin remove tedwester.legion --yes
```

This disables the plugin and removes it from the shell. The plugin also stores
rolling thermal history at `~/.config/omarchy/legion_history.json` and toggle
state at `~/.config/omarchy/legion_state.json`. Delete those files manually
if you no longer want the stored data.

## What the plugin writes

- Sysfs and UEFI nodes under `/sys/` (power profile, GPU mode, battery
  settings, fan controls, Flip to Start) only when you change a setting in
  the panel.
- Audio and touchpad changes apply at runtime via PipeWire and Hyprland and
  are not persisted to disk (a Hyprland reload re-enables the touchpad).
- `~/.config/omarchy/legion_history.json` for short in-panel temperature and
  fan charts.
- `~/.config/omarchy/legion_state.json` for panel state (for example
  GPU overclock, overnight charging, touchpad and fan settings, the saved
  fan curve, and keyboard lighting preferences).
- `~/.local/state/omarchy/powerprofiles/ac` and `.../battery` to remember
  the chosen battery profile per power source, like Omarchy's own panel.

Enabling or disabling the plugin does not modify your bar layout beyond what
Omarchy's plugin enable flow already manages.
