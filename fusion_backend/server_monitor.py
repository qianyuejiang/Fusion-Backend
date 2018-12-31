import logging
import sys
import os
import psutil
import threading
from queue import Queue
import fusion_backend.module


class Module(fusion_backend.module.Module):
    def __init__(self, report_queue: Queue, conf: dict):
        super(Module, self).__init__(report_queue)
        self.__report_interval = conf['interval']
        self.__report_items = conf['items']
        self.__job = threading.Timer(1, self.__do_report)
        self.__task = []

        for task in conf['items']:
            if not hasattr(Monitor, task):
                logging.warning("unknown monitor item '%s'" % task)
            else:
                if task == 'load' and os.name == 'nt':
                    logging.warning("system load info only available on Linux/Unix system")
                    continue
                self.__task.append(getattr(Monitor, task))

    def update(self, info: dict):
        # not accept update
        pass

    def __do_report(self):
        self.__job = threading.Timer(self.__report_interval, self.__do_report).start()
        for task in self.__task:
            task()

    def start(self):
        self.__job.start()

import time
class Monitor:
    __last_update = 0
    __last_network_info = None

    @staticmethod
    def cpu():
        print("%.2f%%" % psutil.cpu_percent())

    @staticmethod
    def network():
        current_time = time.time()
        network_snapshot = psutil.net_io_counters()
        result = {
            'inbound': 0,
            'outbound': 0
        }
        if Monitor.__last_network_info is not None:
            interval = current_time - Monitor.__last_update
            outbound = (network_snapshot[0] - Monitor.__last_network_info[0]) // interval
            inbound = (network_snapshot[1] - Monitor.__last_network_info[1]) // interval
            result = {
                'inbound': inbound,
                'outbound': outbound
            }
        Monitor.__last_update = current_time
        Monitor.__last_network_info = network_snapshot
        print(result)

    @staticmethod
    def load():
        print(os.getloadavg())

    @staticmethod
    def ram():
        print(psutil.virtual_memory().percent)
