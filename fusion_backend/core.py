import json
import logging
import importlib
import threading
from queue import Queue


class Core:

    def __init__(self, config_filename="config.json"):
        self.__config_filename = config_filename
        self.__config_raw_json = None
        self.__module_queue = Queue()
        self.__report_thread = threading.Thread(target=self.__reporter)

    def get_config_filename(self):
        return self.__config_filename

    def load(self):
        with open(self.__config_filename, 'r') as file_handle:
            self.__config_raw_json = json.load(file_handle)

        if "controller" not in self.__config_raw_json:
            logging.warning("no controller address")

        if "node" not in self.__config_raw_json:
            logging.warning("node id not set")

        self.__module_list = []

        if type(self.__config_raw_json['module']) is dict:
            for module_name, module_config in self.__config_raw_json['module'].items():
                # 替换成下划线
                module_name = module_name.replace('-', '_')
                try:
                    module_meta = importlib.import_module(".modules."+module_name, __package__)
                except ImportError:
                    logging.warning("module '%s' not found." % module_name)
                    continue
                module = getattr(module_meta, module_meta.module_name)(self.__module_queue, module_config)
                self.__module_list.append(module)

    def run(self):
        # start reporter
        self.__report_thread.start()

        for module in self.__module_list:
            module.start()

    def __reporter(self):
        while True:
            payload = [self.__module_queue.get()]
            while not self.__module_queue.empty():
                payload.append(self.__module_queue.get_nowait())

            print(payload)
