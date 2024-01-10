from main import light, PCL_CONFIG_SENSOR_MODES, MODE_NO_PI, MODE_NO_CAM, StreamingOutput, MODE_DEBUG_OUTPUT


class PyCamLightControls:
    GPIO_RED = 17
    GPIO_GREEN = 27
    GPIO_BLUE = 22
    camera_configuration = None
    pig_interface = None
    streaming_output = None
    lights = light(0,0,0)
    # Streaming
    streaming_started = False
    camera_running = False

    def __init__(self):
        PyCamLightControls.initialize_pycamlights()

    @staticmethod
    def get_camera_interface():
        if not hasattr(PyCamLightControls, 'camera_interface'):
            PyCamLightControls.camera_interface = Picamera2()
            PyCamLightControls.camera_interface.create_preview_configuration()
        return PyCamLightControls.camera_interface

    @staticmethod
    def reconfigure(mode):
        sc = PyCamLightControls.get_camera_interface()
        if not sc:
            PyCamLightControls.dbg_msg("Problem with camera interface")
            return
        if mode == 'video':
            (x, y) = PCL_CONFIG_SENSOR_MODES[0].get("size")
            PyCamLightControls.dbg_msg(f"Creating video configuration with parameters: \n Output Size x, y: {str(x)}, {str(y)}")
            PyCamLightControls.camera_configuration = sc.create_video_configuration(main={"size": (x, y)})
        elif mode == 'still':
            PyCamLightControls.camera_configuration = sc.create_still_configuration()
        else:
            PyCamLightControls.camera_configuration = sc.create_preview_configuration()
        sc.switch_mode(PyCamLightControls.camera_configuration)

    @staticmethod
    def initialize_pycamlights():

        try:
            PyCamLightControls.lights = light(0, 0, 0)
            PyCamLightControls.dbg_msg("PyCamLights Initializing.")
            if not MODE_NO_PI:
                PyCamLightControls.dbg_msg("PI modules initializing.")
                PyCamLightControls.pig_interface = pigpio.pi()

            if not MODE_NO_CAM:
                PyCamLightControls.dbg_msg("Camera initializing.")
                sc = PyCamLightControls.get_camera_interface()
                sc.start()

        except Exception as e:
            # Log the exception summary to PyCam...dbg_msg
            PyCamLightControls.dbg_msg(f"Exception during initialization: {str(e)}")
            # Handle the exception as required, e.g., exit gracefully or take corrective actions
            PyCamLightControls.dbg_msg("Exiting the application gracefully due to initialization error.")
            # Exit with a non-zero status to indicate an error



    @staticmethod
    def start_camera_stream():

        if PyCamLightControls.streaming_output is None:
            PyCamLightControls.streaming_output = StreamingOutput()

        if not MODE_NO_PI and not MODE_NO_CAM:

            PyCamLightControls.dbg_msg("Accessing camera stream...")
            sc = PyCamLightControls.get_camera_interface()

            PyCamLightControls.reconfigure('video')
            PyCamLightControls.dbg_msg('Starting encoder')
            sc.start_encoder(JpegEncoder(), FileOutput(PyCamLightControls.streaming_output))
        else:
            PyCamLightControls.dbg_msg("NO_PI or NO_CAM activated.")
            return

    @staticmethod
    def stop_camera_stream():
        PyCamLightControls.dbg_msg("No viewers detected. Stopping encoding.")
        sc = PyCamLightControls.get_camera_interface()
        PyCamLightControls.streaming_started = False
        sc.stop_encoding()

    @staticmethod
    def dbg_msg(str):
        if MODE_DEBUG_OUTPUT:
            print(str)

    @staticmethod
    def write_lights():
        interface = PyCamLightControls.pig_interface
        current_lights = PyCamLightControls.lights;
        if MODE_NO_PI:
            PyCamLightControls.dbg_msg("NO_PI mode is on. Write lights returns true and sets the lights to: "+ current_lights.__str__())
            return True

        interface.set_PWM_dutycycle(PyCamLightControls.GPIO_RED, current_lights.red)
        interface.set_PWM_dutycycle(PyCamLightControls.GPIO_GREEN, current_lights.green)
        interface.set_PWM_dutycycle(PyCamLightControls.GPIO_BLUE, current_lights.blue)


    @staticmethod
    def validate_lighting_value(val):
       if (val < 0):
           val = 0
       elif (val > 255):
            val = 255
       return val

    @staticmethod
    def set_lighting(**kwargs):
        red = kwargs.get("red", -1)
        if red != -1 :
            PyCamLightControls.lights.red = PyCamLightControls.validate_lighting_value(red)

        green = kwargs.get("green", -1)
        if green != -1:
            PyCamLightControls.lights.green = PyCamLightControls.validate_lighting_value(green)

        blue = kwargs.get("blue", -1)
        if blue != -1:
            PyCamLightControls.lights.blue = PyCamLightControls.validate_lighting_value(blue)

        PyCamLightControls.write_lights()

    @staticmethod
    def clear_lighting():
        PyCamLightControls.dbg_msg("Clearing lighting values")
        PyCamLightControls.set_lighting(red=0,green=0,blue=0)

    @staticmethod
    def access_camera_lores_image():
        sc = PyCamLightControls.get_camera_interface()
        PyCamLightControls.reconfigure('preview')
        data = io.BytesIO()
        sc.capture_file(data, format='jpeg')
        return data.getvalue()

    @staticmethod
    def access_camera_still_image():
        sc = PyCamLightControls.get_camera_interface()
        PyCamLightControls.reconfigure('still')
        data = io.BytesIO()
        sc.capture_file(data, format='jpeg')
        return data.getvalue()
