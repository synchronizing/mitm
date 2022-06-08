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
    middlewares=[middleware.HTTPLog],
    certificate_authority = crypto.CertificateAuthority()
)
mitm.run()
```

This will start a proxy on port `8888` that is capable of intercepting all HTTP traffic (with support for SSL/TLS) and log all activity.

## Extensions

`mitm` can be customized through the implementations of middlewares and protocols. 

[Middlewares](https://synchronizing.github.io/mitm/docs/internals.html#mitm.core.Middleware) are event-driven hooks that are called when connections are made, requests are sent, responses are received, and connections are closed. 

[Protocols](https://synchronizing.github.io/mitm/docs/internals.html#mitm.core.Protocol) are implementations on _how_ the data flows between the client and server, and is responsible for the nitty-gritty details of the protocol. Out of the box `mitm` supports HTTP and HTTPS.

## Example

Using the example above we can send a request to the server via another script:

```python
import requests

proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
requests.get("https://httpbin.org/anything", proxies=proxies, verify=False)
```

Which will lead to the following being logged where `mitm` is running in:

```
2022-06-08 15:07:10 INFO     MITM server started on 127.0.0.1:8888.
2022-06-08 15:07:11 INFO     Client 127.0.0.1:64638 has connected.
2022-06-08 15:07:11 INFO     Client 127.0.0.1:64638 to mitm: 

→ CONNECT httpbin.org:443 HTTP/1.0

2022-06-08 15:07:12 INFO     Client 127.0.0.1:64638 has connected to server 34.206.80.189:443.
2022-06-08 15:07:12 INFO     Client 127.0.0.1:64638 to 34.206.80.189:443: 

→ GET /anything HTTP/1.1
→ Host: httpbin.org
→ User-Agent: python-requests/2.26.0
→ Accept-Encoding: gzip, deflate
→ Accept: */*
→ Connection: keep-alive

2022-06-08 15:07:12 INFO     Server 34.206.80.189:443 to client 127.0.0.1:64638: 

← HTTP/1.1 200 OK
← Date: Wed, 08 Jun 2022 19:07:12 GMT
← Content-Type: application/json
← Content-Length: 396
← Connection: keep-alive
← Server: gunicorn/19.9.0
← Access-Control-Allow-Origin: *
← Access-Control-Allow-Credentials: true
← 
← {
←   "args": {}, 
←   "data": "", 
←   "files": {}, 
←   "form": {}, 
←   "headers": {
←     "Accept": "*/*", 
←     "Accept-Encoding": "gzip, deflate", 
←     "Host": "httpbin.org", 
←     "User-Agent": "python-requests/2.26.0", 
←     "X-Amzn-Trace-Id": "Root=1-62a0f360-774052c80b60f4ea049f5665"
←   }, 
←   "json": null, 
←   "method": "GET", 
←   "origin": "xxx.xxx.xxx.xxx", 
←   "url": "https://httpbin.org/anything"
← }

2022-06-08 15:07:27 INFO     Server 34.206.80.189:443 has disconnected.
2022-06-08 15:07:27 INFO     Client 127.0.0.1:64638 has disconnected.
```
