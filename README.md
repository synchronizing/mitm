# 👨‍💻 mitm: Man in the Middle

<p align="center">

<a href="https://synchronizing.github.io/mitm/">
    <img src="https://github.com/synchronizing/mitm/actions/workflows/docs-publish.yaml/badge.svg">
  </a>

  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg">
  </a>
</p>

A customizable man-in-the-middle proxy with support for HTTP and HTTPS capturing.

## Installing

I'm currently working on getting PyPi's `mitm` page. As of right now, you can install via GitHub:

```
pip install http://github.com/synchronizing/mitm
```

Note that OpenSSL 1.1.1 or greater is required.

## Documentation

Documentation can be found [here](https://synchronizing.github.io/mitm/). 

## Using

By itself `mitm` is not very special. You can boot it up and view debug messages quite easily:

```python
from mitm import MITM, Config
import logging

config = Config(log_level=logging.DEBUG)
MITM.start(config)
```

`mitm` becomes more useful when you either inherit and extend `mitm.MITM`, or utilize the built-in middleware system.

### Inheriting

For more complex modifications to `mitm` you can inherit from `mitm.MITM` to modify the default behavior of how the proxy works. Things like modifying the default TLS configuration, modifying connection behavior, or even changing client behavior can be done.

### Middleware

`mitm` has support for custom middlewares to allow programmatic customizations to incoming and outgoing web requests. To initialize a middleware, simply create a class that inherits from `mitm.Middleware`:

```python
from mitm import MITM, Config, Middleware

class PrintFlow(Middleware):
    async def client_data(self, request) -> bytes:
        print("Client sent:\n\n\t", request, "\n")
        return request

    async def server_data(self, response) -> bytes:
        print("Server replied:\n\n\t", response, "\n")
        return response

config = Config()
config.add_middleware(PrintFlow)
MITM.start(config)
```

Running the above, and then in a different script running:

```python
import requests

proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
requests.get("https://httpbin.org/anything", proxies=proxies, verify=False)
```

Will yield the following print-out:

```
2021-11-09 12:36:10 INFO     Booting up server on 127.0.0.1:8888.
2021-11-09 12:36:16 INFO     Client 127.0.0.1:54275 has connected.
Client sent:

	 b'CONNECT httpbin.org:443 HTTP/1.0\r\n\r\n'

Client sent:

	 b'GET /anything HTTP/1.1\r\nHost: httpbin.org\r\nUser-Agent: python-requests/2.26.0\r\nAccept-Encoding: gzip, deflate\r\nAccept: */*\r\nConnection: keep-alive\r\n\r\n'

Server replied:

	 b'HTTP/1.1 200 OK\r\nDate: Tue, 09 Nov 2021 17:36:17 GMT\r\nContent-Type: application/json\r\nContent-Length: 394\r\nConnection: keep-alive\r\nServer: gunicorn/19.9.0\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Credentials: true\r\n\r\n{\n  "args": {}, \n  "data": "", \n  "files": {}, \n  "form": {}, \n  "headers": {\n    "Accept": "*/*", \n    "Accept-Encoding": "gzip, deflate", \n    "Host": "httpbin.org", \n    "User-Agent": "python-requests/2.26.0", \n    "X-Amzn-Trace-Id": "Root=1-618ab191-4187d50815febd015b589e63"\n  }, \n  "json": null, \n  "method": "GET", \n  "origin": "69.65.87.201", \n  "url": "https://httpbin.org/anything"\n}\n'

2021-11-09 12:36:17 INFO     Successfully closed connection with 127.0.0.1:54275
```

You can modify the request and response data in the middleware before returning. You can read more of this in the documentation.
