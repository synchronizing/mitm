---
name: mitm
description: See the HTTP and HTTPS requests a command makes, with full headers and bodies, by running it through the mitm proxy. Use when asked what a CLI, script, SDK, or test sends over the network; to reverse engineer or document an API from real traffic; or to debug failing HTTP calls, auth headers, redirects, or TLS errors.
---

# mitm

`mitm -- <command>` runs the command with its HTTP(S) traffic routed through a local intercepting proxy, and prints each request/response exchange to stderr. The command's stdout is untouched, and its exit code is passed through.

Install with `pip install mitm` if `mitm --version` fails.

## Pick the right mode

| Goal | Command |
|---|---|
| Which endpoints are called? | `mitm -- <command>` |
| Exact headers and bodies | `mitm -v -- <command>` |
| Many requests, or analysis you will query | `mitm --json -o traffic.jsonl -- <command>` |
| Full, untruncated bodies | add `--max-body 0` |

Options go before `--`. A command may have side effects (it really runs), so capture once with `--json -o` rather than re-running to see more detail.

## Reading the output

Default mode prints one line per exchange, prefixed with `┊` to separate it from the command's own stderr:

```
  ┊ GET https://api.github.com/zen → 200 OK (text/plain, 35 B, 45 ms)
  ┊ CONNECT api.example.invalid:443 ✗ cannot connect to api.example.invalid:443: nodename nor servname provided, or not known
```

`✗` marks a failure and states why. `(no response)` means the connection closed before a response.

`--json` writes one object per exchange:

```
{"time", "duration_ms", "request": {"method", "url", "version", "headers": [[name, value], ...], "body", "body_size", "truncated"}, "response": {"status", "reason", "version", "headers", "body", "body_size", "truncated"}, "error"}
```

`body` is decompressed text, or `null` for binary data. `request` or `response` is `null` when missing. Useful queries:

```bash
jq -r '"\(.request.method) \(.request.url) \(.response.status)"' traffic.jsonl         # overview
jq 'select(.error or .response.status >= 400)' traffic.jsonl                          # failures
jq '.request.headers[] | select(.[0] | ascii_downcase == "authorization")' traffic.jsonl  # auth
```

Treat captured credentials (Authorization headers, cookies, API keys) as secrets: don't repeat them in full to the user unless asked.

## When traffic is missing or fails

| Symptom | Cause | Fix |
|---|---|---|
| `no traffic captured` | The command ignores `HTTP(S)_PROXY` | Fix the port and pass the proxy explicitly, e.g. `mitm -p 8899 -- tool --proxy http://127.0.0.1:8899` |
| `✗ TLS handshake with the client failed` | The client doesn't trust mitm's CA (Java, browsers, Go on macOS, certificate pinning) | Point the client at the CA file (path printed by `mitm` with no command), or trust it system-wide |
| `✗ cannot connect to ...` | DNS, network, or upstream TLS failure | The message is the real cause; mitm is not at fault |
| Node.js not captured | Node.js before 24 ignores proxy variables | Use Node.js 24+, or `undici`'s `EnvHttpProxyAgent` |

HTTP/2-only clients (such as gRPC) and non-HTTP protocols are not supported.

## Standalone proxy

`mitm` with no command runs a proxy on `127.0.0.1:8888` (`-p` changes the port) and prints the CA certificate path. Point clients at it with `--proxy http://127.0.0.1:8888` and trust the CA. Browsing to `http://127.0.0.1:8888/` serves the certificate with install steps for each platform.
