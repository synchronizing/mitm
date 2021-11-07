# 👨‍💻 mitm: Man in the Middle

A customizable man-in-the-middle proxy with support for HTTP and HTTPS capturing.

## Installing

I'm currently working on getting PyPi's `mitm` page. As of right now, you can install via GitHub:

```
pip install http://github.com/synchronizing/mitm
```

Note that OpenSSL 1.1.1 or greater is required.

## Documentation

Documentation can be found [here](). PDF version of docs can be found [here]().

## Using

By itself `mitm` is not very special. You can boot it up and view debug messages quite easily:

```python
from mitm import MITM, Config
import logging

config = Config(log_level=logging.DEBUG)
mitm = MITM(config)
mitm.start()
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
        print("Client sent:\n\n", request.decode())
        return request

    async def server_data(self, response) -> bytes:
        print("Server replied:\n\n", response.decode())
        return response

mitm = MITM()
mitm.start()
```

Running the above, and then in a different script running:

```python
import requests

proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
requests.get("https://httpbin.org/anything", proxies=proxies, verify=False)
```

Will yield the following print-out:

```
2021-11-05 16:32:57 INFO     Booting up server on 127.0.0.1:8888.
2021-11-05 16:33:00 INFO     Client 127.0.0.1:57373 has connected.
Client sent:

CONNECT httpbin.org:443 HTTP/1.0


Client sent:

GET /anything HTTP/1.1
Host: httpbin.org
User-Agent: python-requests/2.26.0
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive


Server replied:

HTTP/1.1 200 OK
Date: Fri, 05 Nov 2021 20:33:01 GMT
Content-Type: application/json
Content-Length: 396
Connection: keep-alive
Server: gunicorn/19.9.0
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true

{
  "args": {}, 
  "data": "", 
  "files": {}, 
  "form": {}, 
  "headers": {
    "Accept": "*/*", 
    "Accept-Encoding": "gzip, deflate", 
    "Host": "httpbin.org", 
    "User-Agent": "python-requests/2.26.0", 
    "X-Amzn-Trace-Id": "Root=1-618594fd-2027236d11ccb6a7334a5800"
  }, 
  "json": null, 
  "method": "GET", 
  "origin": "174.64.123.133", 
  "url": "https://httpbin.org/anything"
}

2021-11-05 16:33:01 INFO     Successfully closed connection with 127.0.0.1:57373.
```

You can modify the request and response data in the middleware before returning. You can read more of this in the documentation.
