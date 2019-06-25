# 👨🏼‍💻 Man In The Middle

A simple Python project that creates a man-in-the-middle proxy utilizing the standard `Asyncio` library. This project allows you to intercept HTTP and HTTPS traffic via a simple proxy service.

![img](https://i.imgur.com/ehPTMCh.png)

This program does not utilize advance tactics like `sslbump`, but rather a very primitive (and often prevented) method of simply replying back to the client with forged certificates. To accomplish a man-in-the-middle attack with TLS this program will generate a self-signed key/certificate that will be utilized to talk back and forth with the client, while simultaneously talking with the destination server. If you imagine a typical connection being:
```
client <-> server
```
This program will do the following:
```
client <-> mitm (server) <-> mitm (emulated client) <-> server
```
Where the client speaks with the `mitm (server)`, and on behalf of the client, the `mitm (emulated client)` speaks to to the server. The HTTP/HTTPS request and response data is then captured in the middle and printed to console.

This project was originally programmed for an advance public proxy management tool and not actually for reasons of exploit. I do caution those that wish to use this for harm, and do not condone the use of this software for such reasons. 

## Requirements

* You must have OpenSSL 1.1.1 or greater.
* [PyOpenSSL](https://github.com/pyca/pyopenssl): Generate the SSL certificate and key.
* [http-parser](https://github.com/benoitc/http-parser): Parse the http request coming into the server.
* [term-color](https://pypi.org/project/termcolor/): Prettify the outputs.

## Installing

Simply clone the project, install, and use.

```bash
$ git clone https://github.com/synchronizing/mitm
$ cd mitm
$ pip install .
```

## Using

Initializing the proxy is fairly easy.

```python
from mitm.server import ManInTheMiddle
import asyncio

mitm = ManInTheMiddle(host="127.0.0.1", port=8080)
asyncio.run(mitm.start())
```

Once the server is up and running you may either redirect any traffic to the proxy via explicit methods:

```python
import requests
proxies = {"http": "127.0.0.1:8888", "https": "127.0.0.1:8888"}
requests.get("http://api.ipify.org?format=json", proxies=proxies, verify=False).text
requests.get("https://api.ipify.org?format=json", proxies=proxies, verify=False).text
```

Or implicit, via setting the environmental variables `http_proxy` and `https_proxy`, and then using `requests` or `aiohttp` without setting proxies.

```bash
export http_proxy=http://127.0.0.1:8888
export https_proxy=http://127.0.0.1:8888
```

Either way will work.
