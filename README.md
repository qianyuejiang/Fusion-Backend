# Fusion-Backend
The backend management platform for Fusion-Panel

## Core

The core of the backend is designed as a module loader. Its priority is to load modules based on `config.json` and handle communications with the controller server through Fusion-API.

## Fusion-API

Fusion-API is an API using customized network protocol to enable a secure and efficient communication between backend and controller.

Fusion-API use json for data exchange, and can be transmit through HTTP protocol or raw TCP.

The format of Fusion-API is listed below.

```text
{
  ModuleName1: {
    // module defined format
  },
  ModuleName2: {
    // module defined format
  }...
}
```
The Core of Fusion-Backend will not trying to parse the data inside module level, but to send the data dict to specified module directly.

## Modules
Modules are which the services running on. This includes but not limits to shadowsocks, v2ray, or any customized modules.
Please note that the Core **only** handles communications.

### Server Monitor

You can use server-monitor module to monitor you node server.

An example configuration is listed below.

```json
"server-monitor": {
  "items": ["cpu", "load", "ram", "network"],
  "interval": 1
}
```

This module will report a group of server information you specified in `item` in a const interval, which you can set in `interval` in unit seconds.

Items that currently supported are as follows.

- cpu
- network
- ram
- load

#### CPU

The usage of cpu in percentage.

#### network

The network activities information of node server.

You will get `uplink` and `downlink` speed in `Byte/s` in report after you enable this item.

#### ram

The usage of ram in percentage.

#### load

The load info of current server. This item only works in \*nix system. In other words, you won't get load information on Windows.

You will get 1 minutes, 5 minutes and 15 minutes server load info in report if you enable this item.

### Shadowsocks

You can use this module to start and manage a shadowsocks server for multi user.

This module only support shadowsocks-server in python version currently.

To enable this module, simply add configuration below inside your module configuration.

```json
"shadowsocks": {
  "manager_address": "127.0.0.1:7805",
  "server": "0.0.0.0"
}
```

As the module use shadowsocks multi-user management api to communicate with shadowsocks-server. You should setup a `manager_address` for socket communication use.

Shadowsocks manager support two types of socket, the TCP socket and the Unix Domain Socket.

The TCP socket works on both \*nix and Windows. To use tcp socket, just join the ip address and port with a `:`.

For example, if you want the shadowsocks-manager listen at `127.0.0.1` with port `7805`, set `manager_address` to `"127.0.0.1:7805"` will work. 

For security reasons, it is recommended to listen to **loop back address**(`127.0.0.1` for ipv4 and `::1` for ipv6) instead of a address that could be access from the internet.

Unix Domain Socket only works on \*nix system, but it has better performance in IPC.

To use Unix Domain Socket, set `manager_address` to a valid sock path.

For example, you can set `manager_address` to `/tmp/run/shadowsocks-manager.sock` to use Unix Domain Socket in communication.

## Relay

With this module, you can easily set up a dynamic **Forward Proxy** for node relay purpose.

This module supports TCP forward based on port, and UDP forward based on UDP session.

An example configuration is listed below.

```json
"relay": {
  "port_begin": 2000,
  "port_end": 2100,
  "relay_addr": ["127.0.0.1", "::"],
  "rules": {
    "udp": {
      "1234": "127.0.0.1:4567",
      "1235": "127.0.0.1:2333"
    }, "tcp": {
      "1070": "127.0.0.1:1080"
    }
  },
  "multiprocessing": false
}
```

You can specify the port range in `port_begin` and `port_end`. When you create a proxy rule that has a source port out of the port range, the proxy rule would be ignored and a warning message would be logged.

The `relay_addr` specified the source address for this module to bind with.

The `rules` item specified the initial proxy rules applied to the module when start up.

There are two sets of sub-rules that you can use in `rules` item. You can specify udp proxy rules in `udp` and TCP proxy rules in `tcp`, 