import pigpio
import os
import numpy as np
import cv2
import base64
import threading
import time

from flask import Flask, request, jsonify, render_template, make_response, Response, url_for

# Initialize pigpio
MODE_NO_PI = True
MODE_DEBUG = True

PCL_CONFIG_RESOLUTION_X = 320
PCL_CONFIG_RESOLUTION_Y = 240
PCL_CONFIG_FRAMERATE = 24


app = Flask(__name__)


class light:
    def __init__(self, red, green, blue):
        self.red = red
        self.green = green
        self.blue = blue
    def __str__(self):
        return "RGB:<"+str(self.red)+", "+str(self.green)+", "+str(self.blue)+">"

class PyCamLightControls:
    GPIO_RED = 27
    GPIO_GREEN = 22
    GPIO_BLUE = 17
    camera_thread = None
    camera_interface = None
    pig_interface = pigpio.pi()
    lights = light(0,0,0)

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
        interface.set_PWM_dutycycle(PyCamLightControls.GPIO_RED, current_lights.blue)

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
            
        PyCamLightControls.dbg_msg(f"Setting RGB values: Red={red}, Green={green}, Blue={blue}");
        PyCamLightControls.write_lights()

    @staticmethod
    def clear_lighting():
        PyCamLightControls.dbg_msg("Clearing lighting values")
        PyCamLightControls.set_lighting(red=0,green=0,blue=0)

    @staticmethod
    def access_camera_stream():

        if MODE_NO_PI:
            PyCamLightControls.dbg_msg("NO_PI activated, no camera present. Generating camera stream. ")
            yield from PyCamLightControls.stream_synthetic_camera()
        else:
            PyCamLightControls.dbg_msg("Accessing camera stream...")
            rawCapture = picamera.array.PiRGBArray(camera)
            camera = PyCamLightControls.camera_interface


            camera.resolution = (PCL_CONFIG_RESOLUTION_X, PCL_CONFIG_RESOLUTION_Y)
            camera.framerate = PCL_CONFIG_FRAMERATE

            for _ in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):

                image = rawCapture.array
                ret, jpeg = cv2.imencode('.jpg', image)
                # Yield the image in a format suitable for streaming
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

                # Clear the stream for the next frame
                rawCapture.truncate(0)

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
    def pull_cv_obj():
        image = np.empty((PCL_CONFIG_RESOLUTION_Y * PCL_CONFIG_RESOLUTION_X * 3,), dtype=np.uint8)
        if MODE_NO_PI:
            PyCamLightControls.dbg_msg("NO_PI mode is on. No camera is present. Returning empty image.")
            image = PyCamLightControls.generate_smiley_face(PCL_CONFIG_RESOLUTION_X,PCL_CONFIG_RESOLUTION_Y)
            return image.reshape((PCL_CONFIG_RESOLUTION_Y, PCL_CONFIG_RESOLUTION_X,3))

        PyCamLightControls.dbg_msg("Accessing still image.");
        PyCamLightControls.camera_interface.capture(image, 'bgr')
        return image.reshape((PCL_CONFIG_RESOLUTION_Y, PCL_CONFIG_RESOLUTION_X,3))

    @staticmethod
    def access_still_image():
        img = PyCamLightControls.pull_cv_obj();
        return img

    @staticmethod
    def initialize_pycamlights():
        PyCamLightControls.lights = light(0,0,0)
        PyCamLightControls.dbg_msg("PyCamLights Initializing.")
        if not MODE_NO_PI:
            PyCamLightControls.dbg_msg("PI modules initializing.")
            PyCamLightControls.camera_interface = picamera.PiCamera(framerate=PCL_CONFIG_FRAMERATE, resolution=(PCL_CONFIG_RESOLUTION_X, PCL_CONFIG_RESOLUTION_Y))
            PyCamLightControls.pig_interface = pigpio.pi()

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

    response = Response(PyCamLightControls.access_camera_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')
    return response


@app.route('/camera', methods=['GET'])
def access_still_image():
    page = request.args.get('page', '0')

    image_obj = PyCamLightControls.access_still_image()
    ret, jpeg = cv2.imencode('.jpg', image_obj)

    if page is '1':
        response = make_response(jpeg.tobytes())
        response.headers['Content-Type'] = 'image/png'
        return response

    encodedImage = base64.b64encode(jpeg).decode('utf-8')
    encodedImageUrl = f"data:image/jpeg;base64,{encodedImage}"
    return render_template("still.html", imageData=encodedImageUrl)

@app.route('/')
def index_page():
    return render_template("index.html")



if __name__ == '__main__':

    PyCamLightControls.initialize_pycamlights()
    app.run(host='0.0.0.0', port=8080)