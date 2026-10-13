# 👨‍💻 mitm

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

## Documentation

Documentation can be found [**here**](https://synchronizing.github.io/mitm/).

## Using

### Command line

`mitm` can wrap any command and log the HTTP & HTTPS requests it makes:

```
$ mitm -- curl -s https://api.github.com/zen
  ┊ GET https://api.github.com/zen → 200 OK (text/plain, 19 B, 44 ms)
Accessible for all.
```

The `┊` lines are the intercepted traffic (stderr). Everything else is the command's normal output (stdout), so it is safe to pipe. `mitm` sets `HTTP_PROXY`, `HTTPS_PROXY`, and the certificate environment variables (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, etc.) on the command automatically, and exits with the command's exit code.

```bash
mitm                                      # Start proxy on default port.
mitm -p 9999                              # Start proxy on port 9999.
mitm -- curl https://example.com          # Capture curl's traffic.
mitm -- python my_script.py               # Capture a script's traffic.
mitm -v -- python my_script.py            # Capture a script's traffic, with headers and bodies.
mitm --json -o traffic.jsonl -- npm ci    # Capture npm's traffic as JSON.
```

Using `-v` will also log the headers and bodies of each request:

```
$ mitm -v -- curl -s https://httpbin.org/post -H 'Content-Type: application/json' -d '{"stream":false}' -o /dev/null
  ┊ POST https://httpbin.org/post HTTP/1.1
  ┊ Host: httpbin.org
  ┊ User-Agent: curl/8.7.1
  ┊ Accept: */*
  ┊ Content-Type: application/json
  ┊ Content-Length: 16
  ┊
  ┊ {"stream":false}
  ┊
  ┊ HTTP/1.1 200 OK (application/json, 427 B, 43 ms)
  ┊ Date: Tue, 13 Oct 2026 02:16:43 GMT
  ┊ Content-Type: application/json
  ┊ Content-Length: 427
  ┊ ...
```

Using `--json` will log each request as a JSON object, one per line:

```json
{
  "time": "2026-10-13T02:16:43.409Z",
  "duration_ms": 108,
  "request": {"method": "GET", "url": "https://api.github.com/zen", "version": "HTTP/1.1", "headers": [["Host", "api.github.com"], ...], "body": "", "body_size": 0, "truncated": false},
  "response": {"status": 200, "reason": "OK", "version": "HTTP/1.1", "headers": [...], "body": "Accessible for all.", "body_size": 19, "truncated": false},
  "error": null
}
```

Note that bodies are decompressed (gzip & deflate) and decoded into text. Binary bodies are `null`, and bodies are cut short after `--max-body` bytes (4096 by default, `0` for no limit). Requests that fail are logged with the reason:

```
  ┊ CONNECT api.example.invalid:443 ✗ Unable to connect to api.example.invalid:443 (nodename nor servname provided, or not known).
```

Only commands that respect the `HTTP_PROXY` and `HTTPS_PROXY` environment variables can be captured. This covers curl, wget, Python (requests, httpx, urllib, pip), Node.js 24+, Deno, Go, Ruby, git, and most HTTP libraries. If nothing is captured, `mitm` will let you know. Some commands use their own list of trusted certificates instead of the environment variables above (e.g. browsers, Java, and Go on macOS), and need the certificate to be installed (see below).

### Library

Using the default values for the `MITM` class:

```python
from mitm import MITM, protocol, middleware

mitm = MITM(
    host="127.0.0.1",
    port=8888,
    protocols=[protocol.HTTP],
    middlewares=[middleware.HTTPLog],
)
mitm.run()
```

This will start a proxy on port `8888` that is capable of intercepting all HTTP traffic (with support for SSL/TLS) and log all activity.

The proxy can also be used as an async context manager. Use port `0` to listen on any free port:

```python
async with MITM(port=0) as mitm:
    print(mitm.port)
```

## Certificates

`mitm` generates a certificate authority the first time it runs, and reuses it after that. Commands wrapped with `mitm --` trust it automatically. For anything else (browsers, phones, other machines), browse to `http://localhost:8888` while the proxy is running to download and install the certificate. Platform-specific formats and instructions are on the page.

## Extensions

`mitm` can be customized through the implementations of middlewares and protocols.

[Middlewares](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Middleware) are event-driven hooks that are called when connections are made, requests are sent, responses are received, and connections are closed (or fail). Only the hooks that are needed have to be implemented:

```python
from mitm import MITM, Middleware, middleware


class Redact(Middleware):
    async def client_data(self, connection, data):
        return data.replace(b"hunter2", b"*******")


MITM(middlewares=[Redact, middleware.HTTPLog]).run()
```

[Protocols](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Protocol) are implementations on _how_ the data flows between the client and server, and is used to implement [application layer](https://en.wikipedia.org/wiki/Application_layer) protocols and/or more complex extensions.

## Agent Skill

An agent skill is available at [`.agents/skills/mitm/`](https://github.com/synchronizing/mitm/tree/master/.agents/skills/mitm) for AI coding agents that support the [SKILL.md](https://agentskills.io) format. To install it for Claude Code:

```
mkdir -p ~/.claude/skills/mitm
curl -fsSL https://raw.githubusercontent.com/synchronizing/mitm/master/.agents/skills/mitm/SKILL.md -o ~/.claude/skills/mitm/SKILL.md
```
