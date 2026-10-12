# AGENTS.md

`mitm` is an HTTP/HTTPS man-in-the-middle proxy: a Python library, plus a CLI that runs a command through the proxy and logs its traffic.

## Layout

| Path | What |
|---|---|
| `mitm/proxy.py` | `MITM` server: accepts connections, picks a protocol, calls middleware hooks, serves the certificate page |
| `mitm/models.py` | `Host`, `Connection`, `Middleware` (optional hooks), `Protocol` (abstract) |
| `mitm/extension/protocol.py` | `HTTP` protocol: `CONNECT` interception, upstream connection, relay |
| `mitm/extension/middleware.py` | `HTTPLog` (exchange logger behind the CLI), `Log` (raw events via `logging`) |
| `mitm/http.py` | Minimal HTTP/1.x parsing: message framing, request/response pairing, body decoding |
| `mitm/crypto.py` | `CertificateAuthority`: persisted CA and per-host certificates |
| `mitm/cli.py` | The `mitm` command |
| `.agents/skills/mitm/SKILL.md` | Skill that teaches agents to use the CLI |

## Commands

```bash
pip install -e ".[dev]"
pytest                             # Offline, a few seconds.
ruff check . && ruff format .
```

## Conventions

- Runtime dependencies are `cryptography` and `platformdirs` only.
- Tests never use the network or the real CA directory. Use the fixtures in `tests/conftest.py`: local origins, port `0`, and the autouse `data` fixture.
- No leading underscores on function, method, or attribute names.
- CLI output and the JSON Lines shape are an interface: when changing them, update `README.md`, `SKILL.md`, and the tests together.
