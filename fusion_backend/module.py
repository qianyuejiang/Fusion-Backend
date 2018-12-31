from abc import ABCMeta
from abc import abstractmethod
from queue import Queue


class Module(metaclass=ABCMeta):

    def __init__(self, report_queue: Queue):
        self.__report_queue = report_queue

    # @abstractmethod
    # def report(self, conf: dict):
    #     pass

    # 用于更新的接口
    @abstractmethod
    def update(self, info: dict):
        pass

    # 启动
    @abstractmethod
    def start(self):
        pass

    def report(self, data: dict):
        self.__report_queue.put(data)
