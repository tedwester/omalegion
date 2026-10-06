from .battery import (
    apply_overnight_policy,
    get_battery,
    get_boot_options,
    set_battery_mode,
    set_flip_to_start,
    set_instant_boot,
    set_overnight,
    set_overnight_window,
    set_usb_charging,
    set_usb_mode,
)
from .capabilities import get_capabilities
from .cooling import (
    get_fan_curve,
    get_fans,
    get_thermals,
    set_fan_fullspeed,
    set_fan_mode,
    set_fan_point,
    set_fan_speed,
)
from .display import get_display, set_brightness, set_hdr, set_overdrive, set_refresh_rate
from .gpu import (
    deactivate_dgpu,
    get_gpu,
    restart_dgpu,
    set_gpu_mode,
    set_gpu_oc,
    set_gpu_oc_delta,
)
from .history import update as update_history
from .input import get_input, set_backlight, set_fn_lock, set_mic_mute, set_speaker_mute, set_speaker_volume, set_touchpad
from .lighting import get_lighting, set_logo_light, set_ports_light, set_white_backlight
from .power import (
    apply_godmode_preset,
    delete_godmode_preset,
    get_power,
    is_custom_mode,
    list_godmode_presets,
    save_godmode_preset,
    set_power,
    set_ppt,
    sync_power_profiles,
)
from .system import get_system
