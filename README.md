# 👨🏼‍💻 Man In The Middle

A simple Python project that creates a man-in-the-middle proxy utilizing the standard `Asyncio` library. As of now, this project does not route the clients traffic to its original location - instead, it blocks and responds with a message (either with or without TLS).

![img](https://i.imgur.com/elflATe.png)

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
