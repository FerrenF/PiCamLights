from enum import Enum


class PYLIGHTCONTEXT(Enum):
    CAMERA_INTERFACE = 'camera_interface'
    CAMERA_INITIALIZED = 'camera_initialized'
    CAMERA_STARTED = 'camera_started'

    PIGPIO_INTERFACE = 'pigpio_interface'
    PIGPIO_INITIALIZED = 'pigpio_initialized'

    CURRENT_LIGHT_VALUE = 'current_light_value'
    CURRENT_LIGHT_STATUS = 'current_light_status'