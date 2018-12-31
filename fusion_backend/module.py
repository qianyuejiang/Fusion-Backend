from abc import ABCMeta
from abc import abstractmethod
from queue import Queue


class Module(metaclass=ABCMeta):

    def __init__(self, report_queue: Queue, module_name: str=None):
        self.__report_queue = report_queue
        self.__report_module_name = module_name

    # 用于更新的接口
    @abstractmethod
    def update(self, info: dict):
        pass

    # 启动
    @abstractmethod
    def start(self):
        pass

    def report(self, data: dict):
        if self.__report_module_name is None:
            report_data = {
                self.__class__.__name__: data
            }
        else:
            report_data = {
                self.__report_module_name: data
            }
        # print(self.__class__.__name__)
        self.__report_queue.put(report_data)
