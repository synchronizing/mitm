# 👨‍💻 mitm

<p align="center">

<a href="https://synchronizing.github.io/mitm/">
    <img src="https://github.com/synchronizing/mitm/actions/workflows/docs-publish.yaml/badge.svg">
  </a>

  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg">
  </a>
</p>

A customizable man-in-the-middle TCP proxy with out-of-the-box support for HTTP & HTTPS¹.

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
2022-02-27 12:19:40 INFO     MITM server started on 127.0.0.1:8080.
2022-02-27 12:19:42 INFO     Client 127.0.0.1:53033 has connected.
2022-02-27 12:19:42 INFO     Client 127.0.0.1:53033 to mitm:

	b'CONNECT httpbin.org:443 HTTP/1.0\r\n\r\n'

2022-02-27 12:19:42 INFO     Connected to server 52.55.211.119:443.
2022-02-27 12:19:42 INFO     Client 127.0.0.1:53033 to server 52.55.211.119:443:

	b'GET /anything HTTP/1.1\r\nHost: httpbin.org\r\nUser-Agent: python-requests/2.26.0\r\nAccept-Encoding: gzip, deflate\r\nAccept: */*\r\nConnection: keep-alive\r\n\r\n'

2022-02-27 12:19:42 INFO     Server 52.55.211.119:443 to client 127.0.0.1:53033:

	b'HTTP/1.1 200 OK\r\nDate: Sun, 27 Feb 2022 17:19:42 GMT\r\nContent-Type: application/json\r\nContent-Length: 396\r\nConnection: keep-alive\r\nServer: gunicorn/19.9.0\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Credentials: true\r\n\r\n{\n  "args": {}, \n  "data": "", \n  "files": {}, \n  "form": {}, \n  "headers": {\n    "Accept": "*/*", \n    "Accept-Encoding": "gzip, deflate", \n    "Host": "httpbin.org", \n    "User-Agent": "python-requests/2.26.0", \n    "X-Amzn-Trace-Id": "Root=1-621bb2ae-38b24f564e3a026c13e948b6"\n  }, \n  "json": null, \n  "method": "GET", \n  "origin": "xx.xxx.xxx.xxx", \n  "url": "https://httpbin.org/anything"\n}\n'

2022-02-27 12:19:47 INFO     Server 52.55.211.119:443 has disconnected.
2022-02-27 12:19:47 INFO     Client 127.0.0.1:53033 has disconnected.
```

---

[1] Note that by "HTTPS" we mean a proxy that supports the `CONNECT` statement and not one that instantly performs a TLS handshake on connection with the client (before a valid HTTP/1.1 exchange). `mitm` is flexible enough that this can be added if needed.
