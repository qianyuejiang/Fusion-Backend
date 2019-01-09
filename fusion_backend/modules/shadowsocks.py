import logging
import socket
import multiprocessing
import time
import queue
import threading
import select
import sys
import json
import fusion_backend.module
try:
    import shadowsocks.manager
except ModuleNotFoundError:
    pass


def get_module(report_queue, conf: dict):
    if "shadowsocks.manager" not in sys.modules:
        logging.error("failed to import shadowsocks server. "
                      "In order to run shadowsocks server, "
                      "you should have shadowsocks-python installed first")
        return None
    manager = ShadowsocksManager(report_queue, conf)
    if not manager.success:
        return None
    return manager


class ShadowsocksManager(fusion_backend.module.Module):
    def __init__(self, report_queue, conf: dict):
        super(ShadowsocksManager, self).__init__(report_queue)
        self.__config = conf
        self.__shadowsocks_config = {}
        self.__control_socket: socket.socket
        self.__shadowsocks_process: multiprocessing.Process
        self.success = True
        self.__method_need_check = True
        self.__user_port = dict()
        self.__manage_send_queue = queue.Queue()
        self.__worker_thread = threading.Thread(target=self.__worker)

        # verify REQUIRED configuration first

        if 'manager_address' not in self.__config:
            logging.error("manager_address not set for shadowsocks")
            self.success = False
            return
        self.__control_addr = self.__config['manager_address']
        self.__control_addr: str
        if ':' in self.__control_addr:
            addr = self.__control_addr.rsplit(':', 1)
            self.__control_addr = addr[0], int(addr[1])
            addrs = socket.getaddrinfo(addr[0], addr[1])
            if addrs:
                family = addrs[0][0]
            else:
                logging.error('invalid address: %s', self.__control_addr)
                self.success = False
                return
        else:
            # unix socket
            family = socket.AF_UNIX
        self.__control_socket = socket.socket(family, socket.SOCK_DGRAM)
        self.__control_socket.setblocking(False)
        if "server" not in self.__config:
            logging.warning("server listening address not set, use 0.0.0.0 as default")
            self.__config['server'] = '0.0.0.0'
        if "timeout" not in self.__config:
            logging.warning("server socket timeout not set, set to 60 by default")
            self.__config['timeout'] = 60
        if "fast_open" not in self.__config:
            self.__config['fast_open'] = False  # don't use tcp fast open by default
        if "method" in self.__config:
            # this is not an error, but we should check method before add port in worker
            self.__method_need_check = False
        self.__shadowsocks_config = {
            "manager_address": self.__config['manager_address'],
            "server": self.__config['server'],
            "timeout": self.__config['timeout'],
            "fast_open": self.__config['fast_open'],
            "port_password": {}
        }
        self.__shadowsocks_process = multiprocessing.Process(target=_start_shadowsocks,
                                                             args=(self.__shadowsocks_config,))

    def start(self):
        self.__shadowsocks_process.start()
        time.sleep(1)   # just wait shadowsocks server start
        # connect to shadowsocks manager
        self.__control_socket.connect(self.__control_addr)

        # start handling data transfer
        self.__worker_thread.start()

        # self.__control_socket.send(b'add: {"server_port": 8001, "password":"7cd308cc059"}')

        self.update([{
            'action': 'add',
            'conf': {
                "server_port": 8001,
                "password": "7cd308cc059",
                "method": "aes-256-cfb"
            }
        }])
        self.update([{
            'action': 'add',
            'conf': {
                "server_port": 8002,
                "password": "7cd308cc059",
                "method": "aes-256-cfb"
            }
        }])

    def __worker(self):
        while True:
            rlist, wlist, elist = select.select([self.__control_socket], [self.__control_socket], [])
            if rlist:
                data = self.__control_socket.recv(1506)
                if b'ok' == data:
                    continue
                if b'stat: ' in data:
                    self.update_stat(data[6:])
            elif wlist:
                try:
                    cfg = self.__manage_send_queue.get_nowait()
                except queue.Empty:
                    continue
                self.__control_socket.send(cfg)
            else:       # timeout, just check if there is sth could be sent
                if self.__manage_send_queue.empty() is not True:
                    cfg = self.__manage_send_queue.get_nowait()
                    self.__control_socket.send(cfg)

    def update(self, info: list):
        print(info)
        for conf in info:
            if conf['action'] == 'add':
                if 'server_port' in conf['conf'] and 'password' in conf['conf']:
                    try:
                        method = conf['conf']['method']
                    except KeyError:
                        if self.__method_need_check:
                            logging.error("shadowsocks server cipher method not set")
                            continue
                        else:
                            method = self.__config['method']
                    payload = {
                        'method': method,
                        'server_port': conf['conf']['server_port'],
                        'password': conf['conf']['password']
                    }
                    self.__manage_send_queue.put(("add:%s" % json.dumps(payload)).encode('ascii'))
                    self.__user_port[str(conf['conf']['server_port'])] = 0
                else:
                    logging.error("invalid configuration syntax, miss port or password")
            elif conf['action'] == 'remove':
                # check if port exist first
                if conf['action'] in self.__user_port:
                    self.__manage_send_queue.put('remove:{"server_port":%d}' % int(conf['conf']['server_port']))

    def update_stat(self, user_stat):
        user_traffic_info = json.loads(user_stat)
        user_traffic_list = [{'port': port, 'traffic': traffic} for port, traffic in user_traffic_info.items()]
        self.report({
            'action': 'stat',
            'data': user_traffic_list
        })


# can't pass instance to sub process
def _start_shadowsocks(shadowsocks_config: dict):
    shadowsocks.manager.run(shadowsocks_config)
    logging.info("shadowsocks server started")
