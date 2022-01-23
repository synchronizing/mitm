# 👨‍💻 mitm

<p align="center">

<a href="https://synchronizing.github.io/mitm/">
    <img src="https://github.com/synchronizing/mitm/actions/workflows/docs-publish.yaml/badge.svg">
  </a>

  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg">
  </a>
</p>

A customizable man-in-the-middle TCP proxy with out-of-the-box support for HTTP & HTTPS.

## Installing

```
pip install mitm
```

Note that OpenSSL 1.1.1 or greater is required.

## Documentation

Documentation can be found [**here**](https://synchronizing.github.io/mitm/). 

## Using

Using the default values for the `MITM` class:

```python
from mitm import MITM, protocol, middleware, crypto

mitm = MITM(
    host="127.0.0.1",
    port=8888,
    protocols=[protocol.HTTP],
    middlewares=[middleware.Log],
    buffer_size=8192,
    timeout=5,
    keep_alive=True,
    ssl_context=crypto.mitm_ssl_default_context(),
)
mitm.run()
```

This will start a proxy on port 8888 that is capable of intercepting all HTTP traffic (with support for `CONNECT`), and log all activity.

#### Protocols

`mitm` comes with a set of built-in protocols, and a way to add your own. `Protocols` and are used to implement custom
[application-layer protocols](https://en.wikipedia.org/wiki/Application_layer) that interpret and route traffic. Out-of-the-box `HTTP` is available.

#### Middlewares

Middleware are used to implement event-driven behavior as it relates to the client and server connection. Out-of-the-box `Log` is available.

### Example

Using the example above we can send a request to the server via another script:

```python
import requests

proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
requests.get("https://httpbin.org/anything", proxies=proxies, verify=False)
```

Which will lead to the following being logged where `mitm` is running in:

```
2021-11-29 10:33:02 INFO     MITM started on 127.0.0.1:8888.
2021-11-29 10:33:03 INFO     Client 127.0.0.1:54771 has connected.
2021-11-29 10:33:03 INFO     Client to server:

	b'CONNECT httpbin.org:443 HTTP/1.0\r\n\r\n'

2021-11-29 10:33:03 INFO     Connected to server 18.232.227.86:443.
2021-11-29 10:33:03 INFO     Client to server:

	b'GET /anything HTTP/1.1\r\nHost: httpbin.org\r\nUser-Agent: python-requests/2.26.0\r\nAccept-Encoding: gzip, deflate\r\nAccept: */*\r\nConnection: keep-alive\r\n\r\n'

2021-11-29 10:33:03 INFO     Server to client:

	b'HTTP/1.1 200 OK\r\nDate: Mon, 29 Nov 2021 15:33:03 GMT\r\nContent-Type: application/json\r\nContent-Length: 396\r\nConnection: keep-alive\r\nServer: gunicorn/19.9.0\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Credentials: true\r\n\r\n{\n  "args": {}, \n  "data": "", \n  "files": {}, \n  "form": {}, \n  "headers": {\n    "Accept": "*/*", \n    "Accept-Encoding": "gzip, deflate", \n    "Host": "httpbin.org", \n    "User-Agent": "python-requests/2.26.0", \n    "X-Amzn-Trace-Id": "Root=1-61a4f2af-2de4362101f0cab43f6407b1"\n  }, \n  "json": null, \n  "method": "GET", \n  "origin": "xxx.xx.xxx.xx", \n  "url": "https://httpbin.org/anything"\n}\n'

2021-11-29 10:33:08 INFO     Client has disconnected.
2021-11-29 10:33:08 INFO     Server has disconnected.
```
