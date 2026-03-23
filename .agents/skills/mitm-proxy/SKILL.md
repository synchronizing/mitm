---
name: mitm-proxy
description: Intercept, inspect, and analyze HTTP/HTTPS traffic from any command or script using the mitm proxy. Use when the user asks to capture network traffic, reverse engineer an API, debug HTTP requests, inspect what a CLI tool sends, or analyze traffic from a script.
---

# MITM Proxy

Intercept and analyze HTTP/HTTPS traffic by wrapping commands with the mitm proxy.

## When to Use

- User wants to see what HTTP requests a command or script makes
- User needs to reverse engineer an API by observing traffic
- User wants to debug HTTP request/response cycles
- User asks to inspect, capture, or sniff network traffic from a CLI tool

## CLI Usage

Wrap any command to capture its traffic:

```bash
mitm -- curl https://api.example.com/endpoint
mitm -- python my_script.py
mitm -- node fetch_data.js
mitm -p 9999 -- wget https://example.com/file.zip
```

The proxy automatically sets `HTTP_PROXY`, `HTTPS_PROXY`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, and `CURL_CA_BUNDLE` environment variables on the child process.

Intercepted traffic appears on stderr with a `┊` gutter prefix. The wrapped command's stdout is untouched and safe to pipe.

```
$ mitm -- curl https://httpbin.org/ip
  ┊ proxy listening on 127.0.0.1:8888
  ┊
  ┊ CONNECT httpbin.org:443 HTTP/1.1
  ┊ Host: httpbin.org:443
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
{"origin": "108.46.224.142"}
```

## Library Usage

For programmatic control, use the Python API:

```python
import asyncio
from mitm import MITM

# Blocking (standalone proxy).
MITM(host="127.0.0.1", port=8888).run()

# Async context manager (start, do work, stop).
async def main():
    async with MITM(port=8888) as m:
        # Proxy is running — send traffic through it.
        ...

asyncio.run(main())
```

## Certificate Installation

The proxy serves a cert download page at `http://{host}:{port}/` with platform-specific formats:

| Route | Format | Platform |
|-------|--------|----------|
| `/cert.pem` | PEM | macOS, Linux |
| `/cert.cer` | DER | iOS, Windows |
| `/cert.crt` | DER | Android |

For devices on the same network, point the browser to the proxy address to download and install the CA certificate.

## Analyzing Traffic

When the user wants to understand what a tool does over the network:

1. Run the command wrapped with `mitm` using `Bash`
2. Read the stderr output — the `┊`-prefixed lines are the intercepted traffic
3. Identify the endpoints, methods, headers, and payloads
4. Summarize the findings: what APIs are called, what data is sent/received, auth patterns, etc.

## Limitations

- Only captures traffic from tools that respect proxy environment variables (covers curl, wget, python-requests, node fetch/axios, Go net/http, and most HTTP libraries)
- Raw TCP/socket connections that bypass HTTP proxy settings are not captured
- The proxy is cooperative (env-var based), not a system-level transparent proxy
