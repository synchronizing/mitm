# 👨‍💻 mitm

<p align="center">

<a href="https://synchronizing.github.io/mitm/">
    <img src="https://github.com/synchronizing/mitm/actions/workflows/docs-publish.yaml/badge.svg">
  </a>

  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg">
  </a>
</p>

A customizable man-in-the-middle TCP proxy with support for HTTP & HTTPS.

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
    certificate_authority = crypto.CertificateAuthority()
)
mitm.run()
```

This will start a proxy on port 8888 that is capable of intercepting all HTTP traffic (with support for SSL/TLS) and log all activity.

## Extensions

`mitm` can be customized through the implementations of middlewares and protocols. 

[Middlewares](https://synchronizing.github.io/mitm/customizing/middlewares.html) are event-driven hooks that are called when a connection is made, request is sent, response is received, and connection is closed. 

[Protocols](https://synchronizing.github.io/mitm/customizing/protocols.html) are implementations on _how_ the data flows between the client and server, and is responsible for the nitty-gritty details of the protocol. Out of the box `mitm` supports HTTP and HTTPS.

## Example

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
