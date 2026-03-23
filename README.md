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

Browse to `http://localhost:8888` while the proxy is running to download the CA certificate:

| Platform | Format | How to install |
|----------|--------|----------------|
| macOS | `.pem` | Keychain Access → Always Trust |
| Linux | `.pem` | `sudo cp mitm-ca.pem /usr/local/share/ca-certificates/mitm.crt && sudo update-ca-certificates` |
| iOS | `.cer` | Settings → VPN & Device Management → install, then Certificate Trust Settings → enable |
| Android | `.crt` | Settings → Security → Install a certificate → CA certificate |
| Windows | `.cer` | Install Certificate → Trusted Root Certification Authorities |

## Library

```python
from mitm import MITM

# Blocking.
MITM().run()
```

```python
# Async.
async with MITM(port=8888) as m:
    ...
```

```python
# Manual lifecycle.
m = MITM()
await m.start()
# ...
await m.stop()
```

## Extending

`mitm` is built around two extension points:

**Middlewares** — event hooks for connection lifecycle, request/response data, and logging. Subclass `Middleware` and pass it in:

```python
from mitm import MITM, Middleware

class MyMiddleware(Middleware):
    async def client_data(self, connection, data):
        print(data)
        return data

MITM(middlewares=[MyMiddleware]).run()
```

**Protocols** — control how data flows between client and server. The default `HTTP` protocol handles HTTP/1.1 with TLS interception. Subclass `Protocol` to support other application-layer protocols.

See the full [documentation](https://synchronizing.github.io/mitm/) for details.

## Agent Skill

An agent skill is available at [`.agents/skills/mitm/`](https://github.com/synchronizing/mitm/tree/master/.agents/skills/mitm) for AI coding agents that support the [SKILL.md](https://agentskills.io) format.
