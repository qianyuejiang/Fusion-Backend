import selectors
import logging
from queue import Queue
import fusion_backend.module
import threading
import socket
import time


_logger = logging.getLogger('Relay')


def get_module(report_queue: Queue, conf: dict):
    relay = Relay(report_queue, conf)
    return relay


def _format_addr(addr):
    return addr[0], addr[1]


class Relay(fusion_backend.module.Module):
    def __init__(self, report_queue, conf):
        super(Relay, self).__init__(report_queue)

        _logger.debug("starting relay...")

        self.__conf = conf
        self.__port_range = (int(conf['port_begin']), int(conf['port_end']))
        self.__selector = selectors.DefaultSelector()

        _logger.debug("relay port from %d to %d" % self.__port_range)

        if conf['multiprocessing'] is False:
            # use multi thread instance
            self.__instance_obj_list = {
                'udp': MultiThreadUDPRelay(),
                'tcp': MultiThreadsRelay()
            }
            self.__instance_list = {
                'udp': threading.Thread(target=self.__instance_obj_list['udp'].run),
                'tcp': threading.Thread(target=self.__instance_obj_list['tcp'].run)
            }
        else:
            _logger.error("Multiple processes are not currently supported")

    def start(self):

        for types in self.__conf['rules'].keys():
            for destination_specifier in self.__conf['rules'][types].keys():
                for relay_addr in self.__conf['relay_addr']:
                    destination = self.__conf['rules'][types][destination_specifier]
                    self.__instance_obj_list[types].add_relay(relay_addr, destination_specifier, destination)

        for instance in self.__instance_list.values():
            instance.start()
        _logger.info("relay started")

    def update(self, info: dict):
        pass


class UDPSession(object):
    def __init__(self):
        self._session_list = dict()

    def get_session(self, address_pair):
        if address_pair not in self._session_list:
            return None
        return self._session_list[address_pair]

    def create_session(self, address1, socket1, address2, socket2):
        if address1 not in self._session_list:
            session_info = _SessionInfo()
            self._session_list[address1] = _SessionPeer(socket2, address2[1], session_info)
            self._session_list[address2] = _SessionPeer(socket1, address1[1], session_info)
        return self._session_list[address1]

    def remove_session(self, address):
        try:
            del self._session_list[address]
        except IndexError:
            pass

    def get_timeout(self, timeout):
        expired_session_list = []
        expire_time = time.time() - timeout
        for addr in self._session_list:
            session = self._session_list[addr]
            session: _SessionPeer
            if session.session_info.last_update < expire_time:
                expired_session_list.append(addr)
                print("session expired:", addr)
        return expired_session_list


class _SessionInfo(object):
    def __init__(self):
        self._last_update = time.time()
        self._traffic = 0

    @property
    def last_update(self):
        return self._last_update

    def get_statistic(self, reset=False):
        statistic = self._traffic
        if reset:
            self._traffic = 0
        return statistic

    def update(self, traffic):
        self._last_update = time.time()
        self._traffic += traffic


class _SessionPeer(object):
    def __init__(self, destination_socket: socket.socket, destination_addr, info: _SessionInfo):
        self.socket = destination_socket
        self.address = destination_addr
        self.session_info = info


class MultiThreadUDPRelay(object):
    def __init__(self):
        self.__selector = selectors.DefaultSelector()
        self._sock_to_destination = dict()
        self._session = UDPSession()

    def add_relay(self, local, local_port, destination: str):
        try:
            local_addrinfo = socket.getaddrinfo(local, local_port)[0]
        except socket.gaierror as e:
            _logger.warning("Invalid local address:'%s:%s'(%s)" % (local, local_port, str(e)))
            return
        ip, port = destination.rsplit(':')
        try:
            destination_addrinfo = socket.getaddrinfo(ip, port)[0]
        except socket.gaierror as e:
            _logger.warning("invalid destination address:'%s'(%s)" % (ip, str(e)))
            return
        _logger.info("Add UDP relay: %s:%d <=> %s:%d" % (_format_addr(local_addrinfo[4]) +
                                                         _format_addr(destination_addrinfo[4])))
        sock = socket.socket(local_addrinfo[0], socket.SOCK_DGRAM)
        sock.bind(local_addrinfo[4])
        self._sock_to_destination[sock] = destination_addrinfo
        self.__selector.register(sock, selectors.EVENT_READ, self._recv)

    def _recv(self, sock: socket.socket, mask):
        local_addr = sock.getsockname()
        data, addr = sock.recvfrom(65535)       # maximum udp packet size
        session = self._session.get_session((local_addr, addr))
        session: _SessionPeer
        # check if the session exist
        if session is None:
            _logger.info("new session from [%s]:%d" % (addr[0], addr[1]))
            # session not exist, we should create a new relay session
            destination_addrinfo = self._sock_to_destination[sock]
            relay_sock = socket.socket(destination_addrinfo[0], socket.SOCK_DGRAM)
            # send data to the destination at first,
            # so the system will automatically bind a address for that socket
            relay_sock.sendto(data, destination_addrinfo[4])
            relay_local_addr = relay_sock.getsockname()
            session = self._session.create_session((local_addr, addr), sock,
                                                   (relay_local_addr, destination_addrinfo[4]), relay_sock)
            self.__selector.register(relay_sock, selectors.EVENT_READ, self._recv)
            _logger.info("udp session created: [%s]:%d,[%s]:%d <> [%s]:%d,[%s]:%d" %
                         (MultiThreadUDPRelay._format_addr(addr) +
                          MultiThreadUDPRelay._format_addr(local_addr) +
                          MultiThreadUDPRelay._format_addr(relay_local_addr) +
                          MultiThreadUDPRelay._format_addr(destination_addrinfo[4])))
        else:
            session.socket.sendto(data, session.address)

        session.session_info.update(len(data))

    def _clear(self, expired_list):
        for addr in expired_list:
            sock = self._session.get_session(addr).socket
            if sock not in self._sock_to_destination:
                _logger.info("close socket: %s:%d" % sock.getsockname())
                self.__selector.unregister(sock)
                sock.close()
            self._session.remove_session(addr)

    def run(self):
        while True:
            events = self.__selector.select(timeout=1)
            for key, mask in events:
                key.data(key.fileobj, mask)
            expired_list = self._session.get_timeout(5)
            if expired_list:
                self._clear(expired_list)


class MultiThreadsRelay(object):
    def __init__(self):
        self.__selector = selectors.DefaultSelector()
        self.__sock_addr_map = dict()
        self.__relay_table = dict()
        self.__send_buffer = dict()

    def add_relay(self, local, local_port, destination: str):
        try:
            local_addrinfo = socket.getaddrinfo(local, local_port)[0]
        except socket.gaierror as e:
            _logger.warning("Invalid local address:'%s:%s'(%s)" % (local, local_port, str(e)))
            return
        ip, port = destination.rsplit(':')
        try:
            destination_addrinfo = socket.getaddrinfo(ip, port)[0]
        except socket.gaierror as e:
            _logger.warning("invalid destination address:'%s'(%s)" % (ip, str(e)))
            return

        _logger.info("Add TCP relay:[%s]:%d <=> [%s]:%d" % (_format_addr(local_addrinfo[4]) +
                                                            _format_addr(destination_addrinfo[4])))
        # create local socket
        sock = socket.socket(local_addrinfo[0], socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.bind(local_addrinfo[4])
        sock.listen()
        self.__selector.register(sock, selectors.EVENT_READ, self._accept)
        # add sock into map
        self.__sock_addr_map[sock] = destination_addrinfo

    def _accept(self, sock: socket.socket, mask):
        conn, addr = sock.accept()

        # create relay socket to destination
        destination_sock = socket.create_connection(self.__sock_addr_map[sock][4])
        destination_sock.setblocking(False)
        # add socket into relay table
        self.__relay_table[conn] = destination_sock
        self.__relay_table[destination_sock] = conn

        _logger.info("create relay: [%s]:%d <=> [%s]:%d" % (_format_addr(addr) +
                                                            _format_addr(destination_sock.getpeername())))

        # create send buffer
        self.__send_buffer[conn] = {
            'buffer': None,
            'send_pos': 0
        }
        self.__send_buffer[destination_sock] = {
            'buffer': None,
            'send_pos': 0
        }
        # add both socket into selector
        self.__selector.register(conn, selectors.EVENT_READ, self._relay_handle)
        self.__selector.register(destination_sock, selectors.EVENT_READ, self._relay_handle)

    def _relay_handle(self, sock, mask):
        if mask & selectors.EVENT_READ:     # could read
            self._read(sock)
        if mask & selectors.EVENT_WRITE:
            self._write(sock)

    def _read(self, sock: socket.socket):
        # socket may not exist in relay table
        if sock not in self.__relay_table:
            return
        _logger.debug("read from sock ('%s':%d)" % _format_addr(sock.getsockname()))
        buffer = self.__send_buffer[self._peer(sock)]
        if buffer['buffer'] is None:
            try:
                buffer['buffer'] = sock.recv(81920)
                _logger.debug("actually read, length: %d" % len(buffer['buffer']))
            except ConnectionAbortedError:
                _logger.info("connection abort while receiving from '%s':%d" % _format_addr(sock.getsockname()))
                buffer['buffer'] = None
            except ConnectionResetError:
                _logger.info("connection reset from '%s':%d" % _format_addr(sock.getsockname()))
                buffer['buffer'] = None
            if not buffer['buffer']:
                _logger.debug("connection closed.")
                buffer['buffer'] = None
            if buffer['buffer'] is None:
                self._clear(sock)
                return
            buffer['send_pos'] = 0
        try:
            buffer['send_pos'] += self._peer(sock).send(buffer['buffer'][buffer['send_pos']:])
        except (ConnectionAbortedError, ConnectionResetError):
            _logger.info("connection abort while sending to '%s':%d" %
                         _format_addr(self.__relay_table[sock].getpeername()))
            self._clear(sock)
            return
        except BlockingIOError:         # send buffer is full
            buffer['send_pos'] = 0      # so the next time we write data to buffer from position 0
        if buffer['send_pos'] == len(buffer['buffer']):     # no more data in buffer
            buffer['buffer'] = None
        else:
            # handle writable event on socket, so we can write to the socket as fast as possible
            self.__selector.modify(self._peer(sock), selectors.EVENT_WRITE | selectors.EVENT_READ, self._relay_handle)
        self.__send_buffer[self._peer(sock)] = buffer

    def _write(self, sock: socket.socket):
        # socket may not exist in relay table
        if sock not in self.__relay_table:
            return
        buffer = self.__send_buffer[sock]
        if buffer['buffer'] is None:
            return
        try:
            buffer['send_pos'] += sock.send(buffer['buffer'][buffer['send_pos']:])
        except (ConnectionAbortedError, ConnectionResetError):
            _logger.info("connection abort while sending to '%s':%d" % _format_addr(sock.getpeername()))
            self._clear(sock)
            return
        except BlockingIOError:         # send buffer is full
            buffer['send_pos'] = 0
        if buffer['send_pos'] == len(buffer['buffer']):     # no more data in buffer
            buffer['buffer'] = None
            self.__selector.modify(sock, selectors.EVENT_READ, self._relay_handle)
        self.__send_buffer[sock] = buffer

    def _clear(self, sock):
        _logger.info("shutdown relay: [%s]:%d <==> [%s]:%d" % (_format_addr(sock.getpeername()) +
                                                               _format_addr(self.__relay_table[sock].getpeername())))
        # clear buffer first
        del self.__send_buffer[sock]
        del self.__send_buffer[self.__relay_table[sock]]

        # unregister from selector
        self.__selector.unregister(sock)
        self.__selector.unregister(self.__relay_table[sock])

        # close socket
        self.__relay_table[sock].close()
        sock.close()

        # delete from relay table
        del self.__relay_table[self.__relay_table[sock]]
        del self.__relay_table[sock]

    def _peer(self, sock):
        return self.__relay_table[sock]

    def run(self):
        _logger.debug("relay instance start")
        while True:
            events = self.__selector.select()
            for key, mask in events:
                key.data(key.fileobj, mask)


