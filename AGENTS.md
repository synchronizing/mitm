# 👨‍💻 mitm

A customizable man-in-the-middle TCP proxy with support for HTTP & HTTPS. It can be used as a library, or from the command line to wrap a command and log its traffic.

## Installing

```
pip install -e ".[dev]"
```

## Testing

```
pytest
ruff check . && ruff format .
```

Note that the tests never connect to the internet. Use the fixtures in `tests/conftest.py` (local servers on any free port, and the `data` fixture that keeps the certificate authority out of the user's data directory).

## Structure

```
mitm/
  cli.py                  — Command line (`mitm -- curl ...`).
  proxy.py                — MITM server.
  models.py               — Host, Connection, Flow, Middleware, Protocol.
  crypto.py               — Certificate authority, and certificates for each host.
  http.py                 — HTTP/1.x parsing, used to log requests and responses.
  cert.html               — Certificate download page.
  extension/
    middleware.py         — Log, HTTPLog.
    protocol.py           — HTTP protocol (with TLS support).
.agents/skills/mitm/      — Agent skill for using the command line.
```

## Conventions

- The only dependencies are `cryptography` and `platformdirs`. Avoid adding more.
- Function, method, and attribute names never start with `_`.
- Code is commented step by step, and documented with Google style docstrings (`Args:`, `Returns:`, `Note:`), like the rest of the code.
- The command line output and the JSON format are documented in `README.md` and the agent skill. Update both (and the tests) when changing them.
