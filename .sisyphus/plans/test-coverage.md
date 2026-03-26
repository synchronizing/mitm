# Meaningful Test Coverage for mitm

## TL;DR

> **Quick Summary**: Add behavior-focused tests for the 5 untested/under-tested modules (parser, item, protocol, proxy, middleware). No forced coverage inflation — every test verifies real production behavior.
> 
> **Deliverables**:
> - `tests/utils/http/test_parser.py` — HTTP request/response parsing state machine
> - `tests/utils/http/test_item.py` — Type wrapper and dict variant tests
> - `tests/extension/test_middleware.py` — Expanded with format function tests
> - `tests/extension/test_protocol.py` — Expanded with resolve/connect tests
> - `tests/test_proxy.py` — Certificate serving integration tests
> - `tests/utils/__init__.py`, `tests/utils/http/__init__.py` — Package scaffolding
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: Task 1 → Tasks 2,3 → Final Verification

---

## Context

### Original Request
Increase test coverage with proper, meaningful tests. No crappy forceful tests — real behavior verification only.

### Interview Summary
**Key Discussions**:
- Coverage target: "Just meaningful gaps" — no specific % target
- CLI testing: Skip entirely — thin glue code, 0% stays
- Focus: parser.py, protocol.py, proxy.py, item.py, middleware.py

**Research Findings**:
- Current coverage: 68% overall (728 stmts, 232 missed)
- Existing tests: 22 tests, 265 lines — real objects, no mocks, pytest-asyncio
- parser.py and item.py are highest ROI — pure functions, no I/O
- protocol.py and proxy.py need real asyncio stream pairs (following test_core.py pattern)
- HTTPLog has `# pragma: no cover` — intentionally excluded

### Metis Review
**Identified Gaps** (addressed):
- "No mocks" principle collides with I/O-heavy code → Resolved: use real asyncio stream pairs for protocol, integration via MITM fixture for proxy
- Test file organization unclear → Resolved: mirror source layout
- `@pytest.mark.asyncio` inconsistency → Resolved: keep decorator for consistency
- New dirs need `__init__.py` → Resolved: scaffolding task in Wave 1
- If tests reveal bugs → Resolved: mark `xfail` and document, don't fix production code

---

## Work Objectives

### Core Objective
Add tests that verify real production behavior across the 5 under-tested modules, following existing test patterns (real objects, no mocks, class-based grouping).

### Concrete Deliverables
- 5 test files (2 new, 3 expanded)
- 2 `__init__.py` package files
- Per-module coverage increase verified

### Definition of Done
- [ ] `uv run pytest tests/ -v --tb=short` → all pass, zero failures
- [ ] `uv run pytest --cov=mitm tests/` → overall coverage > 68%
- [ ] Each target module shows coverage improvement over baseline

### Must Have
- Tests for HTTP parser state machine (parse, compile, feed, round-trip)
- Tests for Item type conversions and operator semantics
- Tests for protocol resolve() with CONNECT/GET/malformed
- Tests for proxy serve_direct() cert download paths
- Tests for middleware format_bytes() with valid/invalid UTF-8

### Must NOT Have (Guardrails)
- NO tests for `cli.py` — decision made, 0% stays
- NO tests for `HTTPLog` — `# pragma: no cover` is intentional
- NO tests for `models.py` — already 100%
- NO tests for abstract base classes (`Protocol`, `Middleware`)
- NO mocks — real objects and real asyncio stream pairs only
- NO new test dependencies (no pytest-mock, hypothesis, factory-boy)
- NO refactoring production code for testability
- NO parametrize beyond 5-7 representative cases per test
- NO tests that verify Python mechanics rather than application behavior

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: YES (tests-after — code already exists)
- **Framework**: pytest + pytest-asyncio + pytest-cov (already installed via `.[dev]`)

### QA Policy
Every task MUST verify coverage improved for its target module using:
```bash
uv run pytest <test_file> -v --cov=mitm.<module> --cov-report=term-missing
```
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — scaffolding + independent tests):
├── Task 1: Test directory scaffolding [quick]
├── Task 4: Expand middleware format function tests [quick]
├── Task 5: Expand protocol resolve/connect tests [unspecified-high]
└── Task 6: Proxy serve_direct integration tests [unspecified-high]

Wave 2 (After Task 1 — tests in new directories):
├── Task 2: HTTP parser tests [unspecified-high]
└── Task 3: Item type wrapper tests [unspecified-high]

Wave FINAL (After ALL tasks — verification):
├── F1: Plan compliance audit [oracle]
├── F2: Code quality review [unspecified-high]
├── F3: Real manual QA [unspecified-high]
└── F4: Scope fidelity check [deep]
-> Present results -> Get explicit user okay

Critical Path: Task 1 → Task 2 → Final Verification
Parallel Speedup: ~50% faster than sequential
Max Concurrent: 4 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 2, 3 |
| 2 | 1 | Final |
| 3 | 1 | Final |
| 4 | — | Final |
| 5 | — | Final |
| 6 | — | Final |

### Agent Dispatch Summary

- **Wave 1**: **4** — T1 → `quick`, T4 → `quick`, T5 → `unspecified-high`, T6 → `unspecified-high`
- **Wave 2**: **2** — T2 → `unspecified-high`, T3 → `unspecified-high`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 4. Expand Middleware Format Function Tests

  **What to do**:
  - Expand existing `tests/extension/test_middleware.py` — add new test classes below the existing `Test_Log` class
  - Add `Test_FormatBytes`: test `format_bytes()` with valid UTF-8 bytes (should decode and strip), invalid UTF-8 bytes (`b"hello\xff"` — should fall back to repr), empty bytes
  - Add `Test_FormatGutter`: test `format_gutter()` with valid UTF-8 (should add `┊` gutter prefix per line), invalid UTF-8 (should fall back to repr with gutter), empty bytes, multi-line input
  - Add `Test_CLILog`: test `CLILog.mitm_started()` writes startup message to stderr, `CLILog.server_connected()` writes server address to stderr, `CLILog.client_data()` writes gutter-formatted data to stderr, `CLILog.server_data()` writes gutter-formatted data to stderr. Use `capsys` or `capfd` pytest fixture to capture stderr output.
  - Test that `CLILog.client_connected()` and `CLILog.client_disconnected()` and `CLILog.server_disconnected()` are no-ops (call them, verify no stderr output)

  **Must NOT do**:
  - Do NOT test `HTTPLog` — it has `# pragma: no cover` and is intentionally excluded
  - Do NOT modify existing `Test_Log` tests
  - Do NOT add mocks — use `capsys`/`capfd` which are built-in pytest fixtures

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 5, 6)
  - **Blocks**: Final
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `tests/extension/test_middleware.py` — Existing test file to expand. Note the class-level shared objects pattern: `log = extension.Log()`, `connection = models.Connection(...)`. Follow this exact pattern for new classes.

  **API/Type References**:
  - `mitm/extension/middleware.py:format_bytes()` (line ~25) — Takes bytes, returns formatted string. Tries UTF-8 decode, falls back to repr on UnicodeDecodeError.
  - `mitm/extension/middleware.py:format_gutter()` (line ~40) — Takes bytes, returns string with `┊` gutter prefix on each line.
  - `mitm/extension/middleware.py:CLILog` — Middleware that writes to `sys.stderr`. Methods: `mitm_started`, `server_connected`, `client_data`, `server_data` write output; `client_connected`, `client_disconnected`, `server_disconnected` are no-ops.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Middleware tests pass and coverage improved
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/extension/test_middleware.py -v --tb=short
      2. Run: uv run pytest tests/extension/test_middleware.py --cov=mitm.extension.middleware --cov-report=term-missing
    Expected Result: All tests pass (existing + new). Coverage for mitm.extension.middleware > 73% (baseline: 73%)
    Evidence: .sisyphus/evidence/task-4-middleware-coverage.txt

  Scenario: format_bytes handles invalid UTF-8 gracefully
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/extension/test_middleware.py -v -k "format" --tb=short
    Expected Result: format_bytes with invalid UTF-8 returns repr fallback, no exceptions
    Evidence: .sisyphus/evidence/task-4-middleware-format.txt
  ```

  **Commit**: YES
  - Message: `test: add middleware format function and CLILog tests`
  - Files: `tests/extension/test_middleware.py`
  - Pre-commit: `uv run pytest tests/extension/test_middleware.py -v --tb=short`

- [ ] 5. Expand Protocol Resolve and Connect Tests

  **What to do**:
  - Expand existing `tests/extension/test_protocol.py` — add new tests below existing `Test_HTTP` class
  - Add `Test_HTTP_Resolve`: test `HTTP.resolve()` with:
    - CONNECT request (`CONNECT example.com:443 HTTP/1.1`) → sets tls=True, extracts host/port
    - Regular GET request with Host header (`GET / HTTP/1.1\r\nHost: example.com`) → sets tls=False, extracts host from header
    - CONNECT with missing target → raises `InvalidProtocol`
    - GET with missing Host header → raises `InvalidProtocol`
    - Request with no method → raises `InvalidProtocol`
  - For resolve() tests: create a real `Connection` with real asyncio reader/writer pairs (following `test_core.py` pattern — spin up local `asyncio.start_server`). Feed the initial request data into the reader, then call `resolve()`.
  - Add `Test_HTTP_Connect`: test `HTTP.connect()` with a real local echo server — verify connection is established and server host/port are populated on the Connection object. Test with TLS=False only (TLS=True requires cert setup which is complex).
  - Optionally test `tls_handshake()` if achievable with real stream pairs and the existing `CertificateAuthority`. If too complex, skip — don't force it.

  **Must NOT do**:
  - Do NOT test `relay()` or `handle()` — these are best verified via integration and are too complex to unit test meaningfully without mocks
  - Do NOT mock asyncio readers/writers — use real stream pairs
  - Do NOT modify existing `Test_HTTP` tests
  - Do NOT test abstract `Protocol` base class

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 4, 6)
  - **Blocks**: Final
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `tests/extension/test_protocol.py` — Existing test file to expand. Has `Test_HTTP` class with `test_init`, `test_resolve`, `test_connect_no_tls`.
  - `tests/test_core.py:test_Host` (lines 9-21) — Pattern for creating real asyncio stream pairs: `asyncio.start_server(handler, "127.0.0.1", 0)` + `asyncio.open_connection(addr[0], addr[1])`

  **API/Type References**:
  - `mitm/extension/protocol.py:HTTP.resolve()` — Takes `Connection` with initial data in `connection.client.reader`. Parses HTTP request, extracts host/port/tls. Sets `connection.server.host` and `connection.server.port`. Raises `InvalidProtocol` on malformed input.
  - `mitm/extension/protocol.py:HTTP.connect()` — Takes `Connection` with resolved host/port. Opens real connection to server. If TLS, performs `tls_handshake()` and sends `200 OK` to client.
  - `mitm/extension/protocol.py:tls_handshake()` — Upgrades stream to TLS using `loop.start_tls()`.
  - `mitm/models.py:Connection` — Holds `client: Host` and `server: Host` with `reader`/`writer` on each.
  - `mitm/models.py:InvalidProtocol` — Exception raised for protocol errors.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Protocol tests pass and coverage improved
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/extension/test_protocol.py -v --tb=short
      2. Run: uv run pytest tests/extension/test_protocol.py --cov=mitm.extension.protocol --cov-report=term-missing
    Expected Result: All tests pass (existing + new). Coverage for mitm.extension.protocol > 58% (baseline: 58%)
    Evidence: .sisyphus/evidence/task-5-protocol-coverage.txt

  Scenario: InvalidProtocol raised for malformed requests
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/extension/test_protocol.py -v -k "invalid or missing or malformed" --tb=short
    Expected Result: All error-case tests pass — InvalidProtocol raised as expected
    Evidence: .sisyphus/evidence/task-5-protocol-errors.txt
  ```

  **Commit**: YES
  - Message: `test: add protocol resolve and connect tests`
  - Files: `tests/extension/test_protocol.py`
  - Pre-commit: `uv run pytest tests/extension/test_protocol.py -v --tb=short`

- [ ] 6. Proxy serve_direct Integration Tests

  **What to do**:
  - Create `tests/test_proxy.py`
  - Use the session-scoped MITM server fixture (already running on `127.0.0.1:8888` via conftest.py autouse)
  - Test `serve_direct()` by sending direct HTTP requests (not proxy requests) to the running server:
    - `GET / HTTP/1.1` → should return HTML cert download page (200 OK, Content-Type: text/html)
    - `GET /cert.pem HTTP/1.1` → should return PEM format certificate (200 OK)
    - `GET /cert.cer HTTP/1.1` → should return DER/ASN1 format certificate (200 OK)
    - `GET /cert.crt HTTP/1.1` → should return DER/ASN1 format certificate (200 OK)
    - `GET /nonexistent HTTP/1.1` → should return 404
  - Test `MITM` as async context manager: verify `async with MITM() as m:` starts server (use a different port like 18889 to avoid conflict), verify server is accessible, verify cleanup on exit
  - Test `MITM.stop()`: start server, stop it, verify port is freed

  **Must NOT do**:
  - Do NOT test `mitm()` handler directly — it's the main proxy handler and is integration-tested via existing `test_mitm.py`
  - Do NOT mock — use real HTTP connections to the running server
  - Do NOT test protocol matching/routing internals

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 4, 5)
  - **Blocks**: Final
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `tests/test_mitm.py` — Pattern for connecting to the running MITM server: `asyncio.open_connection(HOST, PORT)`, send raw HTTP, read response. Import `HOST`, `PORT`, `BUFFER_SIZE` from `conftest`.
  - `tests/conftest.py` — Server fixture runs on `127.0.0.1:8888`. Autouse, session-scoped.

  **API/Type References**:
  - `mitm/proxy.py:MITM.serve_direct()` (line ~153) — Handles direct (non-proxy) requests. Routes by path: `/` → HTML page, `/cert.pem` → PEM cert, `/cert.cer`/`/cert.crt` → ASN1 cert, else → 404. Response format: `HTTP/1.1 STATUS\r\nHeaders\r\n\r\nBody`.
  - `mitm/proxy.py:MITM.__aenter__()` / `__aexit__()` — Async context manager. Calls `start()` on enter, `stop()` on exit.
  - `mitm/proxy.py:MITM.stop()` — Calls `server.close()` + `server.wait_closed()`.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Proxy tests pass and coverage improved
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/test_proxy.py -v --tb=short
      2. Run: uv run pytest tests/test_proxy.py --cov=mitm.proxy --cov-report=term-missing
    Expected Result: All tests pass. Coverage for mitm.proxy > 69% (baseline: 69%)
    Evidence: .sisyphus/evidence/task-6-proxy-coverage.txt

  Scenario: Certificate download paths return correct content types
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/test_proxy.py -v -k "cert or pem or cer or crt" --tb=short
    Expected Result: All cert path tests pass — correct content types and 200 status
    Evidence: .sisyphus/evidence/task-6-proxy-certs.txt

  Scenario: 404 for unknown paths
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/test_proxy.py -v -k "404 or notfound or nonexistent" --tb=short
    Expected Result: Unknown path returns 404 response
    Evidence: .sisyphus/evidence/task-6-proxy-404.txt
  ```

  **Commit**: YES
  - Message: `test: add proxy serve_direct integration tests`
  - Files: `tests/test_proxy.py`
  - Pre-commit: `uv run pytest tests/test_proxy.py -v --tb=short`

- [x] 1. Test Directory Scaffolding

  **What to do**:
  - Create `tests/utils/__init__.py` as empty file
  - Create `tests/utils/http/__init__.py` as empty file
  - These are Python package markers so pytest can discover tests in the new directories

  **Must NOT do**:
  - Add any content to these files beyond empty (match `tests/extension/__init__.py` pattern)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 4, 5, 6)
  - **Blocks**: Tasks 2, 3
  - **Blocked By**: None

  **References**:
  - `tests/extension/__init__.py` — Existing empty `__init__.py` to match pattern
  - `tests/utils/http/` — Target directory that needs to exist for parser and item tests

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Package files exist and are importable
    Tool: Bash
    Steps:
      1. Run: ls -la tests/utils/__init__.py tests/utils/http/__init__.py
      2. Run: uv run python -c "import tests.utils.http"
    Expected Result: Both files exist, import succeeds with no errors
    Evidence: .sisyphus/evidence/task-1-scaffolding.txt
  ```

  **Commit**: YES
  - Message: `test: add test directory scaffolding for utils/http`
  - Files: `tests/utils/__init__.py`, `tests/utils/http/__init__.py`

- [ ] 2. HTTP Parser Tests

  **What to do**:
  - Create `tests/utils/http/test_parser.py`
  - Use class-based grouping: `Test_Headers`, `Test_Request`, `Test_Response`
  - Test `Headers`: construction from dict, compilation to bytes via `_compile()`, multi-value header handling via `__defaultsetitem__()`, list values joining with `", "`
  - Test `Request`: parsing a valid HTTP request line (`GET / HTTP/1.1`), parsing with headers and body, `_compile()` round-trip (parse → compile → compare bytes), `__eq__()` between two parsed requests, `__str__()` output format, `parse()` class method with complete message, ValueError when constructed with partial args
  - Test `Response`: parsing a valid status line (`HTTP/1.1 200 OK`), parsing with headers and body, `_compile()` round-trip, `__str__()` output with arrow direction, `parse()` class method, ValueError for partial args
  - Test `Message.feed()`: feeding bytes incrementally, TypeError when fed non-bytes
  - Test `Message.state`: state transitions from `INCOMPLETE` → `HEADER_ONLY` → `COMPLETE` as data arrives
  - Test round-trip integrity: `compile(parse(raw)) == raw` for representative HTTP messages
  - Test edge cases: headers with colons in value (`Location: http://host:8080/`), empty header value (`Key:\r\n`)

  **Must NOT do**:
  - Do not test abstract `Message._parse_top()` directly
  - Do not parametrize beyond 5-7 cases
  - Do not test every possible HTTP method — use 2-3 representative ones (GET, POST)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 3)
  - **Blocks**: Final
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `tests/extension/test_protocol.py` — Class-based test structure with class-level shared objects (`Test_HTTP`)
  - `tests/test_crypto.py` — Mixed class/function test patterns, assertion style

  **API/Type References**:
  - `mitm/utils/http/parser.py` — Full source: `Headers`, `Message`, `Request`, `Response` classes. `Message.state` returns `MessageState` enum (`INCOMPLETE`, `HEADER_ONLY`, `COMPLETE`). `Request._parse_top()` extracts method/target/protocol. `Response._parse_top()` extracts protocol/status/reason. `Message.feed()` appends bytes to internal buffer. `Headers._compile()` converts headers dict to `b"Key: Value\r\n"` format.
  - `mitm/utils/http/item.py:ItemDict` — Headers internally uses ItemDict for storage

  **External References**:
  - HTTP/1.1 message format: `METHOD SP TARGET SP VERSION CRLF (HEADER CRLF)* CRLF [BODY]`

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Parser tests pass and coverage improved
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/utils/http/test_parser.py -v --tb=short
      2. Run: uv run pytest tests/utils/http/test_parser.py --cov=mitm.utils.http.parser --cov-report=term-missing
    Expected Result: All tests pass. Coverage for mitm.utils.http.parser > 67% (baseline: 67%)
    Evidence: .sisyphus/evidence/task-2-parser-coverage.txt

  Scenario: Round-trip integrity holds
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/utils/http/test_parser.py -v -k "round_trip or roundtrip or compile"
    Expected Result: All round-trip tests pass — parse(compile(parse(raw))) produces equivalent object
    Evidence: .sisyphus/evidence/task-2-parser-roundtrip.txt
  ```

  **Commit**: YES
  - Message: `test: add HTTP parser tests for request/response parsing and state machine`
  - Files: `tests/utils/http/test_parser.py`
  - Pre-commit: `uv run pytest tests/utils/http/test_parser.py -v --tb=short`

- [ ] 3. Item Type Wrapper and Dict Variant Tests

  **What to do**:
  - Create `tests/utils/http/test_item.py`
  - Use class-based grouping: `Test_Item`, `Test_ObjectDict`, `Test_OverloadedDict`, `Test_UnderscoreAccessDict`, `Test_MultiEntryDict`, `Test_ItemDict`
  - Test `Item`: construction from str, bytes, int, bool, None. Properties: `.string`, `.bytes`, `.integer`, `.boolean`, `.original`. Operators: `+Item` (str), `-Item` (int), `Item + Item` (concat), `Item - "sub"` (removal), `Item == Item`, `hash(Item)`, `iter(Item)`, `len(Item)`, `bool(Item)`
  - Test `Item.byte_item()` static method: conversion from str, bytes, int, bool, None, nested Item. TypeError for unsupported types.
  - Test edge cases: `Item(0)` (falsy int — boolean=False, integer=0), `Item(b"")` (empty bytes), `Item("")` (empty string)
  - Test `ObjectDict`: attribute-style access (`d.key` == `d["key"]`), setting via attribute
  - Test `OverloadedDict`: `+` operator (merge dicts), `-` operator (remove keys), in-place variants `+=`, `-=`
  - Test `UnderscoreAccessDict`: underscore/space normalization (`d["content_type"]` == `d["content type"]` == `d["Content-Type"]`), bytes key support
  - Test `MultiEntryDict`: same key set multiple times creates list, single set stays as value
  - Test `ItemDict`: values auto-wrapped in Item, `update()` method wraps values, list values handled correctly

  **Must NOT do**:
  - Do not test `__repr__` beyond a basic existence check — that's Python mechanics
  - Do not parametrize beyond 5-7 cases per test
  - Do not test Item with deeply nested Items (3+ levels) — diminishing returns

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Task 2)
  - **Blocks**: Final
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `tests/extension/test_middleware.py` — Class-based test structure with shared class variables
  - `tests/test_core.py` — Simple assertion patterns for model-like objects

  **API/Type References**:
  - `mitm/utils/http/item.py` — Full source: `Item` (type-agnostic wrapper with operator overloading), `ObjectDict` (attribute access), `OverloadedDict` (arithmetic operators), `UnderscoreAccessDict` (key normalization), `MultiEntryDict` (multi-value), `ItemDict` (auto-wraps values in Item). `Item.__init__` stores original value and type. `Item.byte_item()` is static, converts any supported type to bytes.

  **Acceptance Criteria**:

  **QA Scenarios:**

  ```
  Scenario: Item tests pass and coverage improved
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/utils/http/test_item.py -v --tb=short
      2. Run: uv run pytest tests/utils/http/test_item.py --cov=mitm.utils.http.item --cov-report=term-missing
    Expected Result: All tests pass. Coverage for mitm.utils.http.item > 58% (baseline: 58%)
    Evidence: .sisyphus/evidence/task-3-item-coverage.txt

  Scenario: Edge case types handled correctly
    Tool: Bash
    Steps:
      1. Run: uv run pytest tests/utils/http/test_item.py -v -k "falsy or empty or none or bool"
    Expected Result: All edge case tests pass — Item(0), Item(b""), Item(None) all behave correctly
    Evidence: .sisyphus/evidence/task-3-item-edges.txt
  ```

  **Commit**: YES
  - Message: `test: add Item type wrapper and dict variant tests`
  - Files: `tests/utils/http/test_item.py`
  - Pre-commit: `uv run pytest tests/utils/http/test_item.py -v --tb=short`

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify test exists (read test file, search for test function). For each "Must NOT Have": search test files for forbidden patterns (cli tests, HTTPLog tests, mock imports). Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `uv run pytest tests/ -v --tb=short`. Review all new/changed test files for: mock imports, unnecessary parametrize, tests that verify Python mechanics, `# pragma: no cover` additions. Check test naming follows conventions (Test_ClassName, test_method_name).
  Output: `Tests [N pass/N fail] | Style [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Run full test suite: `uv run pytest tests/ -v --cov=mitm --cov-report=term-missing`. Verify per-module coverage improved: parser.py > 67%, item.py > 58%, protocol.py > 58%, proxy.py > 69%, middleware.py > 73%. Save coverage report to `.sisyphus/evidence/final-qa/coverage-report.txt`.
  Output: `Coverage [old% → new%] per module | Overall [old → new] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual test file. Verify: everything in spec was written (no missing tests), nothing beyond spec was added (no cli tests, no HTTPLog tests, no production code changes). Flag any test that looks "forced" (testing getters/setters, Python mechanics).
  Output: `Tasks [N/N compliant] | Forced Tests [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **Task 1**: `test: add test directory scaffolding for utils/http` — `tests/utils/__init__.py`, `tests/utils/http/__init__.py`
- **Task 2**: `test: add HTTP parser tests for request/response parsing and state machine` — `tests/utils/http/test_parser.py`
- **Task 3**: `test: add Item type wrapper and dict variant tests` — `tests/utils/http/test_item.py`
- **Task 4**: `test: add middleware format function and CLILog tests` — `tests/extension/test_middleware.py`
- **Task 5**: `test: add protocol resolve and connect tests` — `tests/extension/test_protocol.py`
- **Task 6**: `test: add proxy serve_direct integration tests` — `tests/test_proxy.py`

---

## Success Criteria

### Verification Commands
```bash
uv run pytest tests/ -v --tb=short              # All pass, zero failures
uv run pytest --cov=mitm tests/ --cov-report=term-missing  # Coverage improved
```

### Final Checklist
- [ ] All "Must Have" tests present
- [ ] All "Must NOT Have" absent (no cli tests, no HTTPLog tests, no mocks)
- [ ] All tests pass
- [ ] Per-module coverage increased over baseline
- [ ] No new test dependencies added
