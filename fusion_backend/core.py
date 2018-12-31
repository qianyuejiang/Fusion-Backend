import json
import logging
import importlib
import threading
import requests
import json
from queue import Queue


class Core:

    def __init__(self, config_filename="config.json"):
        self.__config_filename = config_filename
        self.__config_raw_json = None
        self.__module_queue = Queue()
        self.__report_thread = threading.Thread(target=self.__reporter)
        self.__do_report = None
        self.__module_list = []

    def get_config_filename(self):
        return self.__config_filename

    def load(self):
        with open(self.__config_filename, 'r') as file_handle:
            self.__config_raw_json = json.load(file_handle)

        if "controller" not in self.__config_raw_json:
            logging.error("no controller address")
            exit(0)

        if "node" not in self.__config_raw_json:
            logging.error("node id not set")
            exit(0)

        self.__do_report = getattr(self, "_%s_report" % self.__config_raw_json['controller_protocol'])

        if type(self.__config_raw_json['module']) is dict:
            for module_name, module_config in self.__config_raw_json['module'].items():
                module_name = module_name.replace('-', '_')
                try:
                    module_meta = importlib.import_module(__package__+".modules."+module_name)
                except ImportError:
                    logging.warning("module '%s' not found." % module_name)
                    continue
                module = getattr(module_meta, 'get_module')(self.__module_queue, module_config)
                if module is None:
                    logging.warning("failed to load '%s'" % module_name)
                else:
                    self.__module_list.append(module)

    def run(self):
        # start reporter
        self.__report_thread.setDaemon(True)
        self.__report_thread.start()

        for module in self.__module_list:
            module.start()

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
