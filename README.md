# 👨‍💻 mitm: Man in the Middle

A customizable man-in-the-middle proxy with support for HTTP and HTTPS.

## Installing

I'm currently working on getting PyPi's `mitm` page. As of right now, you can install via GitHub:

```
pip install http://github.com/synchronizing/mitm
```

Note that OpenSSL 1.1.1 or greater is required.

## Why?

This project was originally built for learning purposes (see old [repo](https://github.com/synchronizing/mitm/tree/d9b3a4932eeab6cba68f84338137c4fd254437a9)), but has been expanded to be a more customizable man-in-the-middle proxy for larger projects.

#### What's the difference between this project and `mitmproxy`?

Purpose, implementation, and customization style. The purpose of `mitm` is to be a light-weight customizable man-in-the-middle proxy intended for larger projects. `mitmproxy` (with its beautiful CLI) seems to be more for _interactive_ request and response tampering and capturing. While it does support everything `mitm` does plus more, it lacks asynchronous support and is clearly much more advance.

## Implementation

`mitm` utilizes a very primative method for HTTP and HTTPS capturing. To accomplish a man-in-the-middle with TLS support `mitm` generates a self-signed key/certificate that is used to speak back-and-forth with the client and destination server. If you imagine a typical connection looking like so:

```
client <-> server
```

`mitm` does the following:

```
client <-> mitm (server) <-> mitm (emulated client) <-> server
```

Where the client speaks with `mitm (server)` and on behalf of the client the `mitm (emulated client)` speaks to to the destination server. The HTTP/HTTPS request and response data is then captured in both pipes and transmitted back and forth.

## Using

By itself `mitm` is not very special. You can boot it up and view debug messages quite easily:

```
mitm --debug start
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


config = Config(middlewares=[PrintFlow])
MITM.start(config)
```

Running the above, and then in a different script running:

```python
import requests

proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
requests.get("https://api.ipify.org?format=json", proxies=proxies, verify=False)
```

Will yield the following printout:

```
2021-11-03 15:30:11 INFO     Booting up server on 127.0.0.1:8888.
2021-11-03 15:30:12 INFO     Client 127.0.0.1:55802 has connected.

Client sent:

CONNECT api.ipify.org:443 HTTP/1.0


Client sent:

GET /?format=json HTTP/1.1
Host: api.ipify.org
User-Agent: python-requests/2.26.0
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive


Server replied:

HTTP/1.1 200 OK
Server: Cowboy
Connection: keep-alive
Content-Type: application/json
Vary: Origin
Date: Wed, 03 Nov 2021 19:30:14 GMT
Content-Length: 23
Via: 1.1 vegur

{"ip":"174.64.123.133"}
```

You can modify the request and response data in the middleware before returning.
