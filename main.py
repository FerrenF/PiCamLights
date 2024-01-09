import pigpio
import os
import io
import numpy as np
import cv2
import base64
import threading
from threading import Condition

import time

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

from flask import Flask, request, jsonify, render_template, make_response, Response, url_for
from flask_socketio import SocketIO, disconnect

# Initialize pigpio
MODE_NO_PI = False
MODE_NO_CAM = False
MODE_DEBUG = True

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

app = Flask(__name__)
socketio = SocketIO(app, port=8080)




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


active_viewers = 0
stream_lock = threading.Lock()
stream_monitor_thread = None
def video_stream_monitor(stop_stream_method):
    global active_viewers ,stream_lock
    while True:
        with stream_lock:
            if active_viewers == 0:
                stop_stream_method()
                return
        time.sleep(10)  # Check every 10 seconds

class PyCamLightControls:
    GPIO_RED = 17
    GPIO_GREEN = 27
    GPIO_BLUE = 22
    camera_configuration = None
    camera_interface = None
    pig_interface = None
    streaming_output = None
    lights = light(0,0,0)
    # Streaming
    streaming_started = False
    camera_running = False
    @staticmethod
    def reconfigure(mode):
        sc = PyCamLightControls.camera_interface
        if mode == 'video':
            (x, y) = PCL_CONFIG_SENSOR_MODES[0].get("size")
            PyCamLightControls.dbg_msg(
                f'Creating video configuration with parameters: \n Outpit Size x, y: "{str(x)},{str(y)}')
            PyCamLightControls.camera_configuration = sc.create_video_configuration(main={"size": (x, y)})
        elif mode == 'still':
            PyCamLightControls.camera_configuration = sc.create_still_configuration()
        else:
            PyCamLightControls.camera_configuration = sc.create_preview_configuration()
        sc.switch_mode(PyCamLightControls.camera_configuration)


    @staticmethod
    def initialize_pycamlights():
        global stream_monitor_thread

        try:
            stream_monitor_thread = threading.Thread(target=video_stream_monitor, kwargs={
                "stop_stream_method": PyCamLightControls.stop_camera_stream})

            PyCamLightControls.lights = light(0, 0, 0)
            PyCamLightControls.dbg_msg("PyCamLights Initializing.")

            if not MODE_NO_PI:
                PyCamLightControls.dbg_msg("PI modules initializing.")
                PyCamLightControls.pig_interface = pigpio.pi()

                if not MODE_NO_CAM:
                    PyCamLightControls.dbg_msg("Camera initializing.")
                    PyCamLightControls.camera_interface = Picamera2()
                    PyCamLightControls.camera_interface.create_preview_configuration()
                    PyCamLightControls.camera_interface.start()

        except Exception as e:
            # Log the exception summary to PyCam...dbg_msg
            PyCamLightControls.dbg_msg(f"Exception during initialization: {str(e)}")
            # Handle the exception as required, e.g., exit gracefully or take corrective actions
            PyCamLightControls.dbg_msg("Exiting the application gracefully due to initialization error.")
            sys.exit(1)  # Exit with a non-zero status to indicate an error

    @staticmethod
    def start_camera_stream():

        if PyCamLightControls.streaming_output is None:
            PyCamLightControls.streaming_output = StreamingOutput()

        if not MODE_NO_PI and not MODE_NO_CAM:

            PyCamLightControls.dbg_msg("Accessing camera stream...")
            sc = PyCamLightControls.camera_interface
            PyCamLightControls.reconfigure('video')
            PyCamLightControls.dbg_msg('Starting encoder')

            sc.start_encoder(JpegEncoder(), FileOutput(PyCamLightControls.streaming_output))
            PyCamLightControls.streaming_started = True  # Update the flag
            PyCamLightControls.stream_monitor_thread.start()
        else:
            PyCamLightControls.dbg_msg("NO_PI or NO_CAM activated. Sending fake stream to buffer.")
            image = np.zeros((height, width, 3), dtype=np.uint8)
            image[:, :] = (255, 0, 0)
            ret, jpeg = cv2.imencode('.jpg', image)
            PyCamLightControls.streaming_output.write(jpeg)


    @staticmethod
    def dbg_msg(str):
        if MODE_DEBUG:
            print(str);

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
            PyCamLightControls.lights.red = validate_lighting_value(red)

        green = kwargs.get("green", -1)
        if green != -1:
            PyCamLightControls.lights.green = validate_lighting_value(green)

        blue = kwargs.get("blue", -1)
        if blue != -1:
            PyCamLightControls.lights.blue = validate_lighting_value(blue)

        PyCamLightControls.write_lights()

    @staticmethod
    def clear_lighting():
        PyCamLightControls.dbg_msg("Clearing lighting values")
        PyCamLightControls.set_lighting(red=0,green=0,blue=0)

    @staticmethod
    def stop_camera_stream():
        PyCamLightControls.dbg_msg("No viewers detected. Stopping encoding.")
        sc = PyCamLightControls.camera_interface
        sc.stop_encoding()



    @staticmethod
    def generate_smiley_face(width=320, height=240):
        """
        Generate a simple smiley face image using NumPy.

        Parameters:
        - width (int): Width of the image.
        - height (int): Height of the image.

        Returns:
        - numpy.ndarray: Smiley face image in BGR format.
        """
        # Create a black background
        image = np.zeros((height, width, 3), dtype=np.uint8)

        # Draw a yellow circle for the face
        center_x, center_y = width // 2, height // 2
        radius = min(width, height) // 3
        cv2.circle(image, (center_x, center_y), radius, (0, 255, 255), -1)  # BGR for yellow: (0, 255, 255)

        # Draw eyes with black circles
        eye_radius = radius // 6
        left_eye_center = (center_x - radius // 2, center_y - radius // 2)
        right_eye_center = (center_x + radius // 2, center_y - radius // 2)
        cv2.circle(image, left_eye_center, eye_radius, (0, 0, 0), -1)  # BGR for black: (0, 0, 0)
        cv2.circle(image, right_eye_center, eye_radius, (0, 0, 0), -1)

        # Draw a smile using an arc
        cv2.ellipse(image, (center_x, center_y + radius // 3), (radius // 2, radius // 2), 0, 0, 180, (0, 0, 0), 2)

        return image

    @staticmethod
    def access_camera_lores_image():
        PyCamLightControls.reconfigure('preview')
        data = io.BytesIO()
        sc.capture_file(data, format='jpeg')
        return data.getvalue()
        
    @staticmethod
    def access_camera_still_image():
        PyCamLightControls.reconfigure('still')
        data = io.BytesIO()
        sc.capture_file(data, format='jpeg')
        return data.getvalue()



# Routes
@app.route('/lights/set', methods=['GET'])
def set_lighting():
    red = int(request.args.get('red', 0))
    green = int(request.args.get('green', 0))
    blue = int(request.args.get('blue', 0))

    PyCamLightControls.set_lighting(red=red, green=green, blue=blue)

    return jsonify({"message": "Lighting values set successfully!"}), 200


@app.route('/lights/off', methods=['GET'])
def clear_lighting():
    PyCamLightControls.clear_lighting()
    return jsonify({"message": "Lighting values cleared successfully!"}), 200

@app.route('/lights/on', methods=['GET'])
def set_lighting_full():
    PyCamLightControls.set_lighting(red=255,green=255,blue=255)
    return jsonify({"message": "Lighting values set to full!"}), 200


def frame_generate():
    while True:
        with PyCamLightControls.streaming_output.condition:
            PyCamLightControls.streaming_output.condition.wait()
            frame = PyCamLightControls.streaming_output.frame

        fps = PCL_CONFIG_SENSOR_MODES[0].get("fps") or 30
        if frame is None:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        time.sleep(1.0 / fps)
@app.route('/stream', methods=['GET'])
def access_camera_stream():

    PyCamLightControls.start_camera_stream()
    return Response(frame_generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/camera', methods=['GET'])
def access_still_image():
    try:

        res = request.args.get('res', 'low')


        if res == 'low':
            image_bytes = PyCamLightControls.access_camera_lores_image()
        elif res == "high":
            image_bytes = PyCamLightControls.access_camera_still_image()
        else:
            image_bites=None
        
        if not image_bytes:
            return "Failed to capture image", 500
            
            
        page = request.args.get('page', '0')
        if page == '0':           
            response = make_response(image_bytes)
            response.headers['Content-Type'] = 'image/jpeg'
            return response     
                
        
        encoded_image = base64.b64encode(image_bytes).decode('utf-8')
        encoded_image_url = f"data:image/jpeg;base64,{encoded_image}"
        return render_template("still.html", imageData=encoded_image_url)

    except Exception as e:
        PyCamLightControls.dbg_msg(f"Error processing request: {e}")
        return "Internal Server Error", 500

@app.route('/')
def index_page():
    return render_template("index.html")

@socketio.on('connect')
def test_connect():
    global active_viewers, stream_lock
    with stream_lock:
        active_viewers += 1
    print('Client connected')

@socketio.on('disconnect')
def test_disconnect():
    global active_viewers, stream_lock
    with stream_lock:
        active_viewers -= 1
    print('Client disconnected')

if __name__ == '__main__':

    PyCamLightControls.initialize_pycamlights()
    socketio.run(app, debug=True)