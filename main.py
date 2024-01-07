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

# Initialize pigpio
MODE_NO_PI = False
MODE_NO_CAM = False
MODE_DEBUG = True

PCL_CONFIG_RESOLUTION_X = 320
PCL_CONFIG_RESOLUTION_Y = 240
PCL_CONFIG_FRAMERATE = 24

PCL_CONFIG_SENSOR_MODES = [{'bit_depth': 10,
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
  'unpacked': 'SGBRG10'}]

app = Flask(__name__)


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
    camera_thread = None
    camera_interface = None
    pig_interface = None
    streaming_output = None
    lights = light(0,0,0)
    streaming_started = False
    @staticmethod
    def start_camera_stream():

        if PyCamLightControls.streaming_started:
            PyCamLightControls.dbg_msg("Camera stream is already active.")
            return

        if MODE_NO_PI or MODE_NO_CAM:
            PyCamLightControls.dbg_msg("NO_PI or NO_CAM activated. Generating camera stream. ")
            yield from PyCamLightControls.stream_synthetic_camera()
        else:
            PyCamLightControls.dbg_msg("Accessing camera stream...")
            sc = PyCamLightControls.camera_interface

            (x, y) = PCL_CONFIG_SENSOR_MODES[0].get("size")
            sc.create_video_configuration(main={"size": (x, y)})

            PyCamLightControls.streaming_output = StreamingOutput()
            sc.start_recording(JpegEncoder(), FileOutput(PyCamLightControls.streaming_output))

            PyCamLightControls.streaming_started = True  # Update the flag
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
    def set_lighting(**kwargs):
        red = kwargs.get("red", -1)
        if red != -1 :
            PyCamLightControls.lights.red = max(0,min(red,255))

        green = kwargs.get("green", -1)
        if green != -1:
            PyCamLightControls.lights.green = max(0,min(green,255))

        blue = kwargs.get("blue", -1)
        if blue != -1:
            PyCamLightControls.lights.blue = max(0,min(blue,255))

        PyCamLightControls.write_lights()

    @staticmethod
    def clear_lighting():
        PyCamLightControls.dbg_msg("Clearing lighting values")
        PyCamLightControls.set_lighting(red=0,green=0,blue=0)



    @staticmethod
    def stop_camera_stream():
        sc = PyCamLightControls.camera_interface
        sc.stop_recording()
    @staticmethod
    def stream_synthetic_camera():
        # Generate synthetic image parameters
        width, height = PCL_CONFIG_RESOLUTION_X, PCL_CONFIG_RESOLUTION_Y
        fps = PCL_CONFIG_FRAMERATE
        delay = 1 / fps

        while True:
            # Generate a synthetic image (for demonstration, a static blue image)
            image = np.zeros((height, width, 3), dtype=np.uint8)
            image[:, :] = (255, 0, 0)  # Set image to blue color

            # Convert the image to JPEG format for streaming
            ret, jpeg = cv2.imencode('.jpg', image)

            # Yield the image in a format suitable for streaming
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            # Introduce delay to simulate the frame rate
            time.sleep(delay)

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
    def access_camera_sensor_mode(preview=False):
        sc = PyCamLightControls.camera_interface
        PyCamLightControls.dbg_msg("Attempting to capture still image from camera.")
        if preview:
            capture_config = sc.create_preview_configuration()
        else:
            capture_config = sc.create_still_configuration()
        data = io.BytesIO()
        sc.switch_mode_and_capture_file(capture_config, data, format='jpeg')
        return data.getvalue()
        
        
    @staticmethod
    def access_camera_lores_image():
        return PyCamLightControls.access_camera_sensor_mode(True)
        
    @staticmethod
    def access_camera_still_image():
        return PyCamLightControls.access_camera_sensor_mode(False)

    @staticmethod
    def initialize_pycamlights():
        PyCamLightControls.lights = light(0,0,0)
        PyCamLightControls.dbg_msg("PyCamLights Initializing.")


        if not MODE_NO_PI:
            PyCamLightControls.dbg_msg("PI modules initializing.")
            PyCamLightControls.pig_interface = pigpio.pi()
            #PyCamLightControls.pig_interface.set_PWM_range(PyCamLightControls.GPIO_RED, 255)
            #PyCamLightControls.pig_interface.set_PWM_range(PyCamLightControls.GPIO_GREEN, 255)
            #PyCamLightControls.pig_interface.set_PWM_range(PyCamLightControls.GPIO_BLUE, 255)

            if not MODE_NO_CAM:
                PyCamLightControls.dbg_msg("Camera initializing.")
                PyCamLightControls.camera_interface = Picamera2()
    
                sc = PyCamLightControls.camera_interface
                sc.configure(sc.create_preview_configuration())
                sc.start()


        camera_thread = threading.Thread(target=access_camera_stream)
        camera_thread.start()

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

@app.route('/stream', methods=['GET'])
def access_camera_stream():


    PyCamLightControls.start_camera_stream()
    def generate():
        while True:
            with PyCamLightControls.streaming_output.condition:
                PyCamLightControls.streaming_output.wait()
                frame = PyCamLightControls.streaming_output.frame
            fps = PCL_CONFIG_SENSOR_MODES[0].get("fps") or 30
            if frame is None:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type:image/jpeg\r\n'
                   b'Content-Length: ' + f"{len(frame)}".encode() + b'\r\n'
                                                                    b'\r\n' + frame + b'\r\n')
            time.sleep(1.0 / fps)
            frame = PyCamLightControls.streaming_output.frame

    response = Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    return response


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



if __name__ == '__main__':

    PyCamLightControls.initialize_pycamlights()
    app.run(host='0.0.0.0', port=8080)