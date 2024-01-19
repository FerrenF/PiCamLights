import argparse
import multiprocessing
import gunicorn.app.base
from multiprocessing import Array, Manager, Value
from signal import SIGHUP
import PyCamLightControls
from PyCamLightsFlaskApp import app

MODE_DEBUG = False
MODE_DEBUG_OUTPUT = True


def number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1


def number_of_threads():
    return number_of_workers() * 4


def dbg_msg(stri):
    if MODE_DEBUG_OUTPUT:
        print(stri)


def app_context():
    global data
    manager_dict = Manager().dict()
    data['multiprocess_manager'] = manager_dict
    return data['multiprocess_manager']


# App Initialization
def initialize():

    global data
    data = {}
    manager_dict = Manager().dict()
    data['multiprocess_manager'] = manager_dict
    initialize_pycamlights()


class StandaloneApplication(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items()
                  if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


if __name__ == '__main__':
    global data
    parser = argparse.ArgumentParser()
    parser.add_argument('--num-workers', type=int, default=number_of_workers())
    parser.add_argument('--num-threads', type=int, default=number_of_threads())
    parser.add_argument('--port', type=str, default='8080')
    args = parser.parse_args()

    options = {
        'bind': '%s:%s' % ('0.0.0.0', args.port),
        'workers': args.num_workers,
    }
    initialize()
    StandaloneApplication(app, options).run()
