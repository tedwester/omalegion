from .battery import get_battery, set_battery_mode, set_overnight, set_usb_charging
from .cooling import get_fans, get_thermals, set_fan_mode, set_fan_speed
from .gpu import deactivate_dgpu, get_gpu, set_gpu_mode, set_gpu_oc
from .history import update as update_history
from .input import get_input, set_backlight, set_fn_lock, set_touchpad
from .power import get_power, is_custom_mode, set_power, set_ppt, sync_power_profiles
from .system import get_system
