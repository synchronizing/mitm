---
name: mitm
description: Intercept, inspect, and analyze HTTP/HTTPS traffic from any command or script using the mitm proxy. Use when the user asks to capture network traffic, reverse engineer an API, debug HTTP requests, inspect what a CLI tool sends, or analyze traffic from a script.
---

# MITM Proxy

Intercept and analyze HTTP/HTTPS traffic by wrapping commands with the mitm proxy.

## When to Use

- User wants to see what HTTP requests a command or script makes
- User needs to reverse engineer an API by observing traffic
- User wants to debug HTTP request/response cycles (headers, auth, redirects, TLS errors)
- User asks to inspect, capture, or sniff network traffic from a CLI tool

If `mitm --version` fails, install it with `pip install mitm`.

## CLI Usage

Wrap any command to capture its traffic:

```bash
mitm -- curl https://api.example.com/endpoint      # One line per request.
mitm -v -- python my_script.py                     # With headers and bodies.
mitm --json -o traffic.jsonl -- node fetch_data.js # As JSON, one request per line.
mitm --max-body 0 -v -- python my_script.py        # With full bodies (4096 bytes by default).
```

Options go before the `--`. Note that the command really runs, so if it has side effects capture it once with `--json -o traffic.jsonl` and query the file, instead of running it again for more detail.

The proxy listens on any free port, and sets `HTTP_PROXY`, `HTTPS_PROXY`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, and similar variables on the command. The command's exit code is passed through.

## Analyzing Traffic

Intercepted traffic appears on stderr with a `┊` gutter prefix. The wrapped command's stdout is untouched and safe to pipe.

```
$ mitm -- curl -s https://api.github.com/zen
  ┊ GET https://api.github.com/zen → 200 OK (text/plain, 19 B, 44 ms)
Accessible for all.
```

Requests that fail are marked with `✗`, followed by the reason. `(no response)` means the connection closed before a response was received.

```
  ┊ CONNECT api.example.invalid:443 ✗ Unable to connect to api.example.invalid:443 (nodename nor servname provided, or not known).
```

With `--json`, each line is an object with `time`, `duration_ms`, `request` (`method`, `url`, `version`, `headers`, `body`, `body_size`, `truncated`), `response` (`status`, `reason`, `version`, `headers`, `body`, `body_size`, `truncated`), and `error`. Headers are `[name, value]` pairs. Bodies are decompressed text, or `null` if binary. For example:

```bash
jq -r '"\(.request.method) \(.request.url) \(.response.status)"' traffic.jsonl          # Overview.
jq 'select(.error or .response.status >= 400)' traffic.jsonl                           # Failures.
jq '.request.headers[] | select(.[0] | ascii_downcase == "authorization")' traffic.jsonl  # Auth headers.
```

When the user wants to understand what a tool does over the network:

1. Run the command wrapped with `mitm` using `Bash`
2. Read the `┊` lines (or the JSON file) for the intercepted traffic
3. Identify the endpoints, methods, headers, and payloads
4. Summarize the findings: what APIs are called, what data is sent/received, auth patterns, etc.

Note that the traffic may contain secrets (`Authorization` headers, cookies, API keys). Do not repeat them in full unless the user asks.

## Troubleshooting

| Output | Cause | Fix |
|---|---|---|
| `no traffic captured` | The command does not respect `HTTP_PROXY`/`HTTPS_PROXY` | Use a fixed port and pass the proxy to the command, e.g. `mitm -p 8899 -- tool --proxy http://127.0.0.1:8899` |
| `✗ Unable to perform the TLS handshake with the client` | The command does not trust the mitm certificate (e.g. Java, browsers, Go on macOS, certificate pinning) | Pass the certificate to the command (its path is printed by `mitm` with no command), or install it system-wide |
| `✗ Unable to connect to ...` | DNS, network, or TLS failure on the server's side | The reason is the real cause, not the proxy |
| Node.js is not captured | Node.js older than 24 ignores the proxy variables | Use Node.js 24+, or undici's `EnvHttpProxyAgent` |

## Library Usage

For programmatic control, use the Python API:

```python
import asyncio
from mitm import MITM

# Blocking (standalone proxy).
MITM(host="127.0.0.1", port=8888).run()


# Async context manager (start, do work, stop).
async def main():
    async with MITM(port=0) as mitm:
        # Proxy is running on 'mitm.port' — send traffic through it.
        ...


asyncio.run(main())
```

## Certificate Installation

Running `mitm` with no command starts a standalone proxy on `127.0.0.1:8888`, and prints the path of its certificate. It also serves a cert download page at `http://{host}:{port}/` with platform-specific formats:

| Route | Format | Platform |
|-------|--------|----------|
| `/cert.pem` | PEM | macOS, Linux |
| `/cert.cer` | DER | iOS, Windows |
| `/cert.crt` | DER | Android |

## Limitations

- Only captures traffic from tools that respect proxy environment variables (covers curl, wget, python-requests, httpx, node fetch, Go net/http, and most HTTP libraries)
- Raw TCP/socket connections that bypass HTTP proxy settings are not captured
- HTTP/2-only clients (e.g. gRPC) are not supported
- The proxy is cooperative (env-var based), not a system-level transparent proxy
