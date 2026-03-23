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

Man-in-the-middle proxy for HTTP & HTTPS. Wrap any command, see every request.

## Install

```
pip install mitm
```

## Quick Start

Wrap a command and watch its traffic:

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
{
  "origin": "108.46.224.142"
}
```

The `┊` lines are intercepted proxy traffic (stderr). Everything else is the command's normal output (stdout). Pipe-safe.

`mitm` sets `HTTP_PROXY`, `HTTPS_PROXY`, and the CA cert env vars automatically on the child process — nothing to configure.

## CLI

```bash
mitm                                   # standalone proxy on :8888
mitm -p 9999                           # custom port
mitm -- curl https://example.com       # wrap a command
mitm -- python my_script.py            # wrap a script
```

## Certificates

Browse to `http://localhost:8888` while the proxy is running to download and install the CA certificate. Platform-specific formats and instructions are on the page.

## Library

Using the default values for the `MITM` class:

```python
from mitm import MITM, CertificateAuthority
from mitm.extension import protocol, middleware

mitm = MITM(
    host="127.0.0.1",
    port=8888,
    protocols=[protocol.HTTP],
    middlewares=[middleware.Log],
    certificate_authority=CertificateAuthority(),
)
mitm.run()
```

The proxy can also be used as an async context manager:

```python
async with MITM() as mitm:
    ...
```

## Extensions

`mitm` is customizable through middlewares and protocols.

[Middlewares](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Middleware) are event-driven hooks called when connections are made, requests are sent, responses are received, and connections are closed.

[Protocols](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Protocol) are implementations on _how_ data flows between client and server, used to implement [application layer](https://en.wikipedia.org/wiki/Application_layer) protocols.

See the full [documentation](https://synchronizing.github.io/mitm/) for details.

## Agent Skill

An agent skill is available at [`.agents/skills/mitm/`](https://github.com/synchronizing/mitm/tree/master/.agents/skills/mitm) for AI coding agents that support the [SKILL.md](https://agentskills.io) format.
