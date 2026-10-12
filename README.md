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

Man-in-the-middle proxy for HTTP and HTTPS. Run a command through it and see every request it makes, whether you're debugging it yourself or your coding agent is.

```
$ mitm -- curl -s https://api.github.com/zen
  ┊ GET https://api.github.com/zen → 200 OK (text/plain, 35 B, 45 ms)
Approachable is better than simple.
```

## Install

```bash
pip install mitm
```

## Usage

```bash
mitm -- curl https://example.com          # one line per request
mitm -v -- python app.py                  # include headers and bodies
mitm --json -o traffic.jsonl -- npm ci    # every exchange as JSON Lines
mitm                                      # standalone proxy on 127.0.0.1:8888
```

`mitm` starts a proxy on a free port and runs the command with `HTTP_PROXY` and `HTTPS_PROXY` pointing at it. It also sets `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS` and similar variables so the command trusts mitm's certificate authority. When the command exits, mitm exits with the same code. Traffic is written to stderr (or `-o FILE`), so the command's stdout stays clean to pipe.

With `-v`, each exchange is printed in full:

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
  ┊ Date: Mon, 12 Oct 2026 21:01:20 GMT
  ┊ Content-Type: application/json
  ┊ Content-Length: 427
  ┊ ...
```

With `--json`, each exchange is one line of JSON:

```json
{
  "time": "2026-10-12T21:00:53.547Z",
  "duration_ms": 43,
  "request": {"method": "GET", "url": "https://api.github.com/zen", "version": "HTTP/1.1", "headers": [["Host", "api.github.com"], ...], "body": "", "body_size": 0, "truncated": false},
  "response": {"status": 200, "reason": "OK", "version": "HTTP/1.1", "headers": [...], "body": "Approachable is better than simple.", "body_size": 35, "truncated": false},
  "error": null
}
```

Bodies are decompressed (gzip, deflate) and decoded as text. Binary bodies are `null`, and bodies are cut off after `--max-body` bytes (default 4096; `0` for no limit). Failures are reported rather than swallowed:

```
  ┊ CONNECT api.example.invalid:443 ✗ cannot connect to api.example.invalid:443: nodename nor servname provided, or not known
```

### What gets captured

Any client that honors `HTTP(S)_PROXY`: curl, wget, Python (requests, httpx, urllib, pip), Node.js 24+, Deno, Go, Ruby, git, and the AWS CLI, among others. If nothing shows up, the command ignores the proxy variables, and mitm says so. Some clients use their own trust store instead of the variables above (browsers, Java, and Go on macOS); install the certificate system-wide for those. HTTP/2-only clients (such as gRPC) and non-HTTP protocols are not supported.

## Certificates

mitm creates its certificate authority on first run, in `~/Library/Application Support/mitm` on macOS or `~/.local/share/mitm` on Linux, and reuses it afterwards. Commands run through `mitm --` trust it automatically. For anything else, such as browsers, phones, or other machines, open `http://127.0.0.1:8888/` while the proxy runs to download the certificate, along with install instructions for each platform.

## For agents

mitm is built to be run by coding agents. It writes plain text with no color codes when its output isn't a terminal, emits JSON Lines with a fixed shape, states errors explicitly, and passes the command's exit code through. The [`mitm` skill](.agents/skills/mitm/SKILL.md) tells agents when and how to use it:

```bash
mkdir -p ~/.claude/skills/mitm
curl -fsSL https://raw.githubusercontent.com/synchronizing/mitm/master/.agents/skills/mitm/SKILL.md -o ~/.claude/skills/mitm/SKILL.md
```

## Library

```python
from mitm import MITM, HTTPLog, Middleware


class Redact(Middleware):
    async def client_data(self, connection, data):
        return data.replace(b"hunter2", b"*******")


MITM(port=8888, middlewares=[Redact, HTTPLog]).run()
```

`MITM` also works as an async context manager. Port `0` picks a free port:

```python
async with MITM(port=0) as proxy:
    print(proxy.port)
```

[Middlewares](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Middleware) are hooks called as connections open, data flows, and connections close or fail; override only the ones you need. [Protocols](https://synchronizing.github.io/mitm/docs/internals.html#mitm.models.Protocol) define how data flows between client and server; HTTP and HTTPS are built in. See the [documentation](https://synchronizing.github.io/mitm/) for details.
