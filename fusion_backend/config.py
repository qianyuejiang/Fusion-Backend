import json
import logging
import importlib
from queue import Queue

class Config:

    def __init__(self, config_filename="config.json"):
        self.__config_filename = config_filename
        self.__config_raw_json = None

    def get_config_filename(self):
        return self.__config_filename

    def load(self):
        with open(self.__config_filename, 'r') as file_handle:
            self.__config_raw_json = json.load(file_handle)

        if "controller" not in self.__config_raw_json:
            logging.warning("no controller address")

        if "node" not in self.__config_raw_json:
            logging.warning("node id not set")

        module_list = []

        if type(self.__config_raw_json['module']) is dict:
            for module_name, module_config in self.__config_raw_json['module'].items():
                # 替换成下划线
                module_name = module_name.replace('-', '_')
                try:
                    module_meta = importlib.import_module("."+module_name, __package__)
                except ImportError:
                    logging.warning("module '%s' not found." % module_name)
                    continue
                module_queue = Queue()
                module = getattr(module_meta, "Module")(module_queue, module_config)
                module.start()

        # print(self.__config_raw_json)
