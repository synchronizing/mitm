# mitm

<p align="center">
  <a href="https://www.pepy.tech/projects/mitm">
    <img src="https://static.pepy.tech/badge/mitm">
  </a>

  <a href="https://github.com/synchronizing/mitm/actions?query=workflow%3ABuild">
    <img src="https://github.com/synchronizing/mitm/workflows/Build/badge.svg?branch=master&event=push">
  </a>

  <a href="https://synchronizing.github.io/mitm/">
    <img src="https://github.com/synchronizing/mitm/actions/workflows/docs-publish.yaml/badge.svg">
  </a>

  <a href="https://coveralls.io/github/synchronizing/mitm?branch=master">
    <img src="https://coveralls.io/repos/github/synchronizing/mitm/badge.svg?branch=master">
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

## CLI

The fastest way to use `mitm` is through the CLI. Run it standalone as a proxy, or wrap any command to capture its traffic:

```bash
# Start the proxy server.
mitm

# Start on a custom port.
mitm -p 9999

# Wrap a command and capture its traffic.
mitm -- curl https://httpbin.org/ip

# Wrap a Python script.
mitm -- python my_script.py
```

When wrapping a command, `mitm` automatically sets `HTTP_PROXY`, `HTTPS_PROXY`, and CA certificate environment variables so the child process routes traffic through the proxy.

Intercepted traffic is displayed with a `┊` gutter prefix while the wrapped command's output flows through normally:

```
$ mitm -- curl https://httpbin.org/ip
  ┊ proxy listening on 127.0.0.1:8888
  ┊
  ┊ CONNECT httpbin.org:443 HTTP/1.1
  ┊ Host: httpbin.org:443
  ┊ User-Agent: curl/8.7.1
  ┊ Proxy-Connection: Keep-Alive
  ┊
  ┊ → 3.231.81.72:443
  ┊ GET /ip HTTP/1.1
  ┊ Host: httpbin.org
  ┊ User-Agent: curl/8.7.1
  ┊ Accept: */*
  ┊
  ┊ HTTP/1.1 200 OK
  ┊ Content-Type: application/json
  ┊ Content-Length: 33
  ┊
  ┊ {
  ┊   "origin": "108.46.224.142"
  ┊ }
  ┊
{
  "origin": "108.46.224.142"
}
```

Proxy traffic goes to stderr; the command's stdout is untouched and safe to pipe.

### Certificate Installation

Browse to `http://localhost:8888` while the proxy is running to download the CA certificate. The page serves certificates in the right format for each platform:

| Platform | Format | Instructions |
|----------|--------|-------------|
| macOS | `.pem` | Add to Keychain Access, set to Always Trust |
| Linux | `.pem` | Copy to `/usr/local/share/ca-certificates/` |
| iOS | `.cer` | Install profile, then enable in Certificate Trust Settings |
| Android | `.crt` | Install via Security settings |
| Windows | `.cer` | Install to Trusted Root Certification Authorities |

## Library

Use `mitm` as a Python library for more control:

```python
from mitm import MITM

mitm = MITM()
mitm.run()
```

Or with async context manager:

```python
import asyncio
from mitm import MITM

async def main():
    async with MITM() as mitm:
        # Proxy is running; do work here.
        ...

asyncio.run(main())
```

Or with manual start/stop:

```python
import asyncio
from mitm import MITM

async def main():
    mitm = MITM()
    await mitm.start()
    # ...
    await mitm.stop()

asyncio.run(main())
```

## Extensions

`mitm` can be customized through middlewares and protocols.

[Middlewares](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Middleware) are event-driven hooks called when connections are made, requests are sent, responses are received, and connections are closed.

[Protocols](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Protocol) are implementations on _how_ data flows between client and server, used to implement [application layer](https://en.wikipedia.org/wiki/Application_layer) protocols.

## Documentation

Full documentation can be found [**here**](https://synchronizing.github.io/mitm/).
