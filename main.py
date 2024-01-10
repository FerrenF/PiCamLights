import io
import base64
from threading import Condition

import time
from flask import Flask, request, jsonify, render_template, make_response, Response

from PyCamLightControls import PyCamLightControls

# Initialize pigpio

pycamlights = PyCamLightControls()
app = Flask(__name__)


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
    PyCamLightControls.set_lighting(red=255, green=255, blue=255)
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


@app.route('/video', methods=['GET'])
def access_camera_stream():
    PyCamLightControls.start_camera_stream()
    return Response(frame_generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stream', methods=['GET'])
def stream_page():

    if request.args.get('page','0') == 'false':
        return access_camera_stream()
    return render_template('stream.html')

@app.route('/camera', methods=['GET'])
def access_still_image():
    try:

        res = request.args.get('res', 'low')

        if res == 'low':
            image_bytes = PyCamLightControls.access_camera_lores_image()
        elif res == "high":
            image_bytes = PyCamLightControls.access_camera_still_image()
        else:
            image_bytes=None
        
        if not image_bytes:
            return "Failed to capture image", 500


        encoded_image = base64.b64encode(image_bytes).decode('utf-8')
        encoded_image_url = f"data:image/jpeg;base64,{encoded_image}"

        page = request.args.get('page', '0')
        if page == 'false':
                response = make_response(image_bytes)
                response.headers['Content-Type'] = 'image/jpeg'
                return response
        return render_template("still.html", imageData=encoded_image_url)

    except Exception as e:
        PyCamLightControls.dbg_msg(f"Error processing request: {e}")
        return "Internal Server Error", 500

@app.route('/')
def index_page():
    return render_template("index.html")



