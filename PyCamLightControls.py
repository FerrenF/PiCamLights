from enum import Enum
from threading import Condition
import io
import pigpio

from picamera2 import Picamera2

from gunicorn_start import app_context, dbg_msg
from constants import PYLIGHTCONTEXT

MODE_NO_PI = False
MODE_NO_CAM = True


PCL_CONFIG_RESOLUTION_X = 320
PCL_CONFIG_RESOLUTION_Y = 240
PCL_CONFIG_FRAMERATE = 24

PCL_CONFIG_SENSOR_MODES = [
    {'bit_depth': 10,
  'crop_limits': (16, 0, 2560, 1920),
  'exposure_limits': (134, None),
  'format': "SGBRG10_CSI2P",
  'fps': 58.92,
  'size': (640, 480),
  'unpacked': 'SGBRG10'},
 {'bit_depth': 10,
  'crop_limits': (0, 0, 2592, 1944),
  'exposure_limits': (92, 760565, None),
  'format': "SGBRG10_CSI2P",
  'fps': 43.25,
  'size': (1296, 972),
  'unpacked': 'SGBRG10'},
 {'bit_depth': 10,
  'crop_limits': (348, 434, 1928, 1080),
  'exposure_limits': (118, 760636, None),
  'format': "SGBRG10_CSI2P",
  'fps': 30.62,
  'size': (1920, 1080),
  'unpacked': 'SGBRG10'},
 {'bit_depth': 10,
  'crop_limits': (0, 0, 2592, 1944),
  'exposure_limits': (130, 969249, None),
  'format': "SGBRG10_CSI2P",
  'fps': 15.63,
  'size': (2592, 1944),
  'unpacked': 'SGBRG10'}
]

class CameraModes(Enum):
    CAMERA_MODE_PREVIEW=0
    CAMERA_MODE_VIDEO=1
    CAMERA_MODE_STILL=2

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class light:
    def __init__(self, red, green, blue):
        self.red = red
        self.green = green
        self.blue = blue
    def __str__(self):
        return "RGB:<"+str(self.red)+", "+str(self.green)+", "+str(self.blue)+">"


class PyCamLightControls:
    GPIO_RED = 17
    GPIO_GREEN = 27
    GPIO_BLUE = 22
    camera_configuration = None

    streaming_output = None

    # Streaming
    streaming_started = False
    camera_running = False

    _context = None
    _camera_interface = None
    _pig_interface = None

    def __init__(self, context):
        PyCamLightControls._context = context
        try:
            PyCamLightControls._init_pigpio()
            PyCamLightControls._initialize_camera()
        except RuntimeError as E:
            dbg_msg("PyCamLights failed to initialize: "+E.__str__())

    @staticmethod
    def pigpio_initialized():
        if not PyCamLightControls.has_context():
            raise RuntimeError("Could not initialize pigpio in app context: missing")
        _ap = PyCamLightControls.get_context()
        return _ap[PYLIGHTCONTEXT.PIGPIO_INITIALIZED]

    @staticmethod
    def get_pigpio_interface():
        _ap = PyCamLightControls.get_context()
        if not _ap:
            raise RuntimeError("Could not retrieve pigpio interface: context missing.")
        return _ap[PYLIGHTCONTEXT.PIGPIO_INTERFACE]

    @staticmethod
    def _init_pigpio():
        if not PyCamLightControls.has_context():
            raise RuntimeError("Could not initialize pigpio in app context: missing")
        _ap = PyCamLightControls.get_context()

        if MODE_NO_PI:
            dbg_msg("NO_PI mode is enabled. Skipping pigpio initialization.")
            return

        if not PyCamLightControls.pigpio_initialized():
            try:
                _ap[PYLIGHTCONTEXT.PIGPIO_INTERFACE] = pigpio.pi()
            except RuntimeError as E:
                dbg_msg("Failed to initialize pigpio: "+E.__str__())
            else:
                _ap[PYLIGHTCONTEXT.PIGPIO_INITIALIZED] = True

    @staticmethod
    def has_context():
        return PyCamLightControls._context is None

    @staticmethod
    def get_context():
        return PyCamLightControls._context

    @staticmethod
    def is_camera_initialized():
        _ap = PyCamLightControls.get_context()
        return _ap[PYLIGHTCONTEXT.CAMERA_INITIALIZED]

    @staticmethod
    def get_camera_interface() -> Picamera2:
        if PyCamLightControls.has_context() and not MODE_NO_CAM:
            _ap = PyCamLightControls.get_context()
            if _ap[PYLIGHTCONTEXT.CAMERA_INITIALIZED] is False:
                PyCamLightControls._initialize_camera()
            return _ap[PYLIGHTCONTEXT.CAMERA_INTERFACE]
        raise RuntimeError("Camera interface is empty.")

    @staticmethod
    def _reconfigure(mode):

        try:
            sc = PyCamLightControls.get_camera_interface()
            if mode == CameraModes.CAMERA_MODE_VIDEO:
                (x, y) = PCL_CONFIG_SENSOR_MODES[0].get("size")
                PyCamLightControls.camera_configuration = sc.create_video_configuration(main={"size": (x, y)})
            elif mode == CameraModes.CAMERA_MODE_STILL:
                PyCamLightControls.camera_configuration = sc.create_still_configuration()
            else:
                PyCamLightControls.camera_configuration = sc.create_preview_configuration()

        except RuntimeError as e:
            dbg_msg("Error creating camera configuration: "+e.__str__())
        else:
            try:
                sc.switch_mode(PyCamLightControls.camera_configuration)
            except RuntimeError as E:
                dbg_msg("Error switching to camera configuration"+E.__str__())
        return

    @staticmethod
    def _initialize_camera():
        _ap = PyCamLightControls.get_context()

        if PyCamLightControls.is_camera_initialized():
            dbg_msg("PyCamLights is already initialized. Skipping.")
            return False

        if MODE_NO_CAM:
            dbg_msg("NO_CAM mode is set. Skipping camera initialization.")
            return False

        _ap[PYLIGHTCONTEXT.CAMERA_INTERFACE] = Picamera2()

        try:
            PyCamLightControls._reconfigure(CameraModes.CAMERA_MODE_PREVIEW)
        except RuntimeError as E:
            dbg_msg("Error encountered reconfiguring camera during initialization.")
        else:
            _ap[PYLIGHTCONTEXT.CAMERA_INITIALIZED] = 'True'

    @staticmethod
    def start_camera_stream():

        if PyCamLightControls.streaming_output is None:
            PyCamLightControls.streaming_output = StreamingOutput()

        if not MODE_NO_PI and not MODE_NO_CAM:

            dbg_msg("Accessing camera stream...")
            sc = PyCamLightControls.get_camera_interface()

            PyCamLightControls._reconfigure(CameraModes.CAMERA_MODE_VIDEO)
            dbg_msg('Starting encoder')
           # sc.start_encoder(JpegEncoder(), FileOutput(PyCamLightControls.streaming_output))
        else:
            dbg_msg("NO_PI or NO_CAM activated.")
            return

    @staticmethod
    def stop_camera_stream():
        dbg_msg("No viewers detected. Stopping encoding.")

    @staticmethod
    def get_light_on():
        _ap = PyCamLightControls.get_context()
        if not _ap:
            dbg_msg("Could not retrieve status of lights. Assuming off.")
            return False
        return _ap[PYLIGHTCONTEXT.CURRENT_LIGHT_STATUS]

    @staticmethod
    def get_lights() -> light:
        _ap = PyCamLightControls.get_context()
        if not _ap:
            return light(0, 0, 0)
        return _ap[PYLIGHTCONTEXT.CURRENT_LIGHT_VALUE]

    @staticmethod
    def set_lights(value):
        _ap = PyCamLightControls.get_context()
        _ap[PYLIGHTCONTEXT.CURRENT_LIGHT_VALUE] = value

    @staticmethod
    def write_lights():

        try:
            interface = PyCamLightControls.get_pigpio_interface()
            current_lights = PyCamLightControls.get_lights()

            if MODE_NO_PI:
                dbg_msg("NO_PI mode is on. Skipping body of write_lights with params: "+ current_lights.__str__())
                return True

        except pigpio.error as E:
            dbg_msg("Problem updating light status: " + E.__str__())

        else:

            try:
                interface.set_PWM_dutycycle(PyCamLightControls.GPIO_RED, current_lights.red)
                interface.set_PWM_dutycycle(PyCamLightControls.GPIO_GREEN, current_lights.green)
                interface.set_PWM_dutycycle(PyCamLightControls.GPIO_BLUE, current_lights.blue)

            except pigpio.error as F:
                dbg_msg("Problem setting light value: " + F.__str__())

    @staticmethod
    def set_lighting_values(**kwargs):

        def validate_lighting_value(val):
            return min(max(val, 0), 255)

        li = PyCamLightControls.get_lights()
        red = kwargs.get("red", -1)
        if red != -1:
            li.red = validate_lighting_value(red)

        green = kwargs.get("green", -1)
        if green != -1:
            li.green = validate_lighting_value(green)

        blue = kwargs.get("blue", -1)
        if blue != -1:
            li.blue = validate_lighting_value(blue)

        PyCamLightControls.write_lights()

    @staticmethod
    def clear_lighting():
        dbg_msg("Clearing lighting values")
        PyCamLightControls.set_lighting_values(red=0, green=0, blue=0)

    @staticmethod
    def _access_camera(mode: CameraModes):
        sc = PyCamLightControls.get_camera_interface()
        PyCamLightControls._reconfigure(mode)
        data = io.BytesIO()
        sc.capture_file(data, format='jpeg')
        return data.getvalue()

    @staticmethod
    def access_camera_lores_image():
        return PyCamLightControls._access_camera(CameraModes.CAMERA_MODE_PREVIEW)

    @staticmethod
    def access_camera_still_image():
        return PyCamLightControls._access_camera(CameraModes.CAMERA_MODE_STILL)


def set_defaults(context):
    context[PYLIGHTCONTEXT.CAMERA_INTERFACE] = None
    context[PYLIGHTCONTEXT.CAMERA_STARTED] = False
    context[PYLIGHTCONTEXT.CAMERA_INITIALIZED] = False
    context[PYLIGHTCONTEXT.PIGPIO_INTERFACE] = None
    context[PYLIGHTCONTEXT.PIGPIO_INITIALIZED] = False
    context[PYLIGHTCONTEXT.CURRENT_LIGHT_STATUS] = 'off'
    context[PYLIGHTCONTEXT.CURRENT_LIGHT_VALUE] = light(0, 0, 0)


def initialize_pycamlights():
    _ap = app_context()
    if not _ap:
            #Problem
        return 0

    set_defaults(_ap)
    PyCamLightControls(_ap)







