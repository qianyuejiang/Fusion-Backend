import socket
import threading
import ipaddress
import logging
import select
import json
import asyncio
from abc import ABCMeta

import tornado.web
import tornado.httpserver
import tornado.ioloop
import tornado.gen
from queue import Queue, Empty

logging.basicConfig(level=logging.INFO)


class Client(threading.Thread):
    def __init__(self, report_queue: Queue):
        self.__report_queue = report_queue
        super(Client, self).__init__()
    
    def run(self):
        pass

    def report(self, raw_json):
        try:
            json_obj = json.loads(raw_json)
            if json_obj['version'] == 1:
                logging.debug("received packet in version 1")
                data = json_obj['data']
            else:
                logging.warning("Invalid packer version. "
                                "Accept packet in version 1, but received in %d" % json_obj['version'])
        except json.JSONDecodeError:
            logging.error("invalid json format")
            return
        except KeyError:
            logging.warning("Invalid packet format!")
            return
        self.__report_queue.put(data)


class HTTPClient(Client):
    def __init__(self, queue: Queue, conf: dict):
        super(HTTPClient, self).__init__(queue)
        self.__conf = conf
        self.__application = tornado.web.Application([
            (r'/', HTTPHandler, dict(conf=conf, reporter=self.report))
        ])
        self.__http_server = tornado.httpserver.HTTPServer(self.__application)
        if type(conf['client']) is str:
            conf['client'] = [conf['client']]
        for client_addr in conf['client']:
            self.__http_server.bind(self.__conf['client_port'], client_addr)

    def run(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.__http_server.start()
        tornado.ioloop.IOLoop.current().start()


# noinspection PyAbstractClass
class HTTPHandler(tornado.web.RequestHandler):
    # conf = None

    def __init__(self, application, request, **kwargs):
        super(HTTPHandler, self).__init__(application, request, **kwargs)
        self.conf = kwargs['conf']
        self.reporter = kwargs['reporter']

    # noinspection PyMethodOverriding
    @tornado.gen.coroutine
    def initialize(self, **kwargs):
        pass

    @tornado.gen.coroutine
    def get(self, *args, **kwargs):
        self.write("<h1>It Works!</h1>")

    @tornado.gen.coroutine
    def post(self, *args, **kwargs):
        if self.request.headers['key'] != self.conf['controller_key']:
            logging.warning("controller key mismatch from '%s'" % self.request.remote_ip)
        if self.request.headers['Content-Type'] == 'application/json':
            self.reporter(self.request.body)


class TCPClient(Client):
    def __init__(self, queue: Queue, conf: dict):
        super(TCPClient, self).__init__(queue)
        self.__sock4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__sock6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.__sock4.setblocking(False)
        self.__sock6.setblocking(False)

        self.__client_sock = []

        if type(conf['client']) is str:
            conf['client'] = [conf['client']]

        for client_addr in conf['client']:
            try:
                res = ipaddress.ip_address(client_addr)
            except ValueError:
                logging.error("invalid ip address '%s'" % client_addr)
                continue
            if type(res) is ipaddress.IPv4Address:
                self.__sock4.bind((client_addr, conf['client_port']))
                logging.info("client server bind on %s:%d" % (client_addr, conf['client_port']))
                self.__client_sock.append(self.__sock4)
                self.__sock4.listen()
            else:
                self.__sock6.bind((client_addr, conf['client_port']))
                logging.info("client server bind on [%s]:%d" % (client_addr, conf['client_port']))
                self.__client_sock.append(self.__sock6)
                self.__sock6.listen()

    def run(self):
        queue_list = {}
        while True:
            readable, writable, exceptional = select.select(self.__client_sock, [], [], 1)
            if readable:
                for sock in readable:
                    if sock is self.__sock4 or sock is self.__sock6:
                        connection, addr = sock.accept()
                        logging.debug("received connection from '%s'" % addr[0])
                        connection.setblocking(False)
                        queue_list[connection] = Queue()    # create receive buffer
                        self.__client_sock.append(connection)   # add socket into read socket list

                    else:
                        data = sock.recv(1024)
                        if data == b'':                     # connection closed
                            logging.debug("connection close by client '%s'" % sock.getpeername()[0])
                            self.__client_sock.remove(sock)
                            del queue_list[sock]        # delete receive queue
                        else:
                            if b'\n' in data:
                                # reach the end if current packet
                                raw_json = ''
                                while True:
                                    try:
                                        raw_json += queue_list[sock].get_nowait()
                                    except Empty:
                                        break
                                mess = data.split(b'\n')
                                raw_json += mess[0]
                                self.report(raw_json)

                                if mess[-1] != b'':
                                    queue_list[sock].put(mess[-1])
                                for packet in mess[1:-1]:
                                    self.report(packet)
                            else:
                                queue_list[sock].put(data)

