import json
import logging
import importlib
import threading
import requests
import json
from queue import Queue

import client


_logger = logging.getLogger('Core')


class Core:

    def __init__(self, config_filename="config.json"):
        self.__config_filename = config_filename
        self.__config_raw_json = None
        self.__module_queue = Queue()
        self.__receive_queue = Queue()
        self.__report_thread = threading.Thread(target=self.__reporter)
        self.__dispatch_thread = threading.Thread(target=self.__dispatch)
        self.__do_report = None
        self.__module_list = {}
        self.__client_instance = None

    def get_config_filename(self):
        return self.__config_filename

    def load(self):
        with open(self.__config_filename, 'r') as file_handle:
            self.__config_raw_json = json.load(file_handle)

        if "controller" not in self.__config_raw_json:
            _logger.error("no controller address")
            exit(0)

        if "node" not in self.__config_raw_json:
            _logger.error("node id not set")
            exit(0)

        _logger.debug("initializing client service...")
        # initialize client
        self.__client_instance = getattr(client, '%sClient' % self.__config_raw_json['client_protocol'].upper())(
            self.__receive_queue, self.__config_raw_json
        )
        self.__client_instance.start()
        _logger.debug("client started with protocol '%s'" % self.__config_raw_json['client_protocol'].upper())

        # initialize report method based on report protocol
        self.__do_report = getattr(self, "_%s_report" % self.__config_raw_json['controller_protocol'])

        if type(self.__config_raw_json['module']) is dict:
            for module_name, module_config in self.__config_raw_json['module'].items():
                module_name = module_name.replace('-', '_')
                try:
                    module_meta = importlib.import_module(__package__+".modules."+module_name)
                except ImportError:
                    _logger.warning("module '%s' not found." % module_name)
                    continue
                module = getattr(module_meta, 'get_module')(self.__module_queue, module_config)
                if module is None:
                    _logger.warning("failed to load '%s'" % module_name)
                else:
                    self.__module_list[module.__class__.__name__] = module
                    _logger.info("module %s loaded" % module.__class__.__name__)
            _logger.info("%d module(s) loaded" % len(self.__module_list))
        else:
            _logger.error("invalid module configuration")
            exit(0)

    def run(self):
        self.__dispatch_thread.setDaemon(True)
        self.__dispatch_thread.start()

        # start reporter
        self.__report_thread.setDaemon(True)
        self.__report_thread.start()

        for module_name in self.__module_list:
            self.__module_list[module_name].start()

    def __reporter(self):
        while True:
            data = [self.__module_queue.get()]
            while not self.__module_queue.empty():
                data.append(self.__module_queue.get_nowait())

            payload = self._get_payload(data)
            self.__do_report(payload)

    def _http_report_init(self):
        # do some initialize work...
        payload = self._get_payload([{
            'core': {
                'action': 'register'
            }
        }])
        self._http_report(payload)

    def _http_report(self, payload):
        headers = {
            'key': self.__config_raw_json['controller_key']
        }
        requests.post(self.__config_raw_json['controller'], json=payload, headers=headers)

    def _tcp_report(self, payload):
        print("tcp report")
        pass

    def _get_payload(self, data):
        return {
                'version': 1,
                'node': self.__config_raw_json['node'],
                'data': data
        }

    def __dispatch(self):
        while True:
            data = self.__receive_queue.get()
            for module_data in data:
                module_name = list(module_data.keys())[0]  # module_data should only have
                if module_name == 'Core':                  # one key which is the module name
                    print("core update")
                else:
                    self.__module_list[module_name].update(module_data[module_name])
