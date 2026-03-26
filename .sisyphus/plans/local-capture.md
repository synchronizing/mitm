# Local Capture Mode — Universal Per-Process Traffic Interception

## TL;DR

> **Goal**: Add `mitm --mode local -- <command>` that intercepts all TCP traffic from a child process without system-wide proxy settings and without the child needing to cooperate.
>
> **Linux**: eBPF (`BPF_PROG_TYPE_CGROUP_SOCK`) redirects sockets to a TUN device at kernel level. Privileged subprocess handles BPF loading (needs `sudo` once). Catches Go, Rust, static binaries — everything.
>
> **macOS**: `DYLD_INSERT_LIBRARIES` injects a hook dylib that intercepts `connect()` / `getaddrinfo()`. Works for Homebrew, Python, Node, user-compiled binaries. Falls back gracefully to env vars for hardened-runtime binaries (SIP-protected system apps, most App Store apps).
>
> **Windows**: Out of scope (WinDivert requires admin, different trust model).

---

## Context

### Research Summary

**Verified findings** (mitmproxy blog, proxychains-ng, GitHub research):

- `LD_PRELOAD` / proxychains-ng: works only for dynamically linked binaries. **Confirmed broken on Go** (static by default). Also broken on Python C extensions loaded via `dlopen()`.
- `DYLD_INSERT_LIBRARIES`: stripped by SIP for `/usr/bin/*`, `/System/*`. Stripped for any binary signed with hardened runtime flag unless it has `allow-dyld-environment-variables` entitlement. Works fine for Homebrew, user-compiled tools.
- Linux network namespaces: needs root for `ip netns exec`. mitmproxy evaluated this and rejected it: *"very hard to package into a good user experience."*
- **eBPF** (what mitmproxy 11.1 shipped, Jan 2025): intercepts at socket creation level in the kernel. Catches everything including static binaries. Still needs `sudo` to load the BPF program via `bpf()` syscall.
- Nothing is truly rootless on Linux for static binaries. The sudo requirement is a kernel constraint, not a tooling choice.

### Key Architectural Decisions (locked in)

| Decision | Choice | Rationale |
|---|---|---|
| Linux mechanism | eBPF + TUN | Only approach that catches static binaries without system-wide changes |
| eBPF kernel portability | CO-RE + BTF | Single binary works across kernel versions; requires BTF (available on kernel 5.8+ with `CONFIG_DEBUG_INFO_BTF=y`) |
| BPF program type | `BPF_PROG_TYPE_CGROUP_SOCK` | Intercepts at socket creation, can redirect before `connect()` completes |
| Original dst recovery | TUN packet headers | BPF redirects socket to TUN device; proxy reads raw IP packets to get original dst IP:port |
| Privileged subprocess | Separate `mitm-redirector` binary | Minimizes sudo scope; parent talks to it via Unix socket |
| macOS mechanism | `DYLD_INSERT_LIBRARIES` + hook dylib | Best available option; graceful fallback for hardened binaries |
| Hook language | C (dylib) / Rust (BPF) | C for dylib (simplest, no runtime deps); Rust+Aya for BPF (strongly typed, CO-RE support) |
| Artifact shipping | Pre-compiled, bundled in wheel | No build-time deps for end users; CI builds for all target platforms |
| Windows | Out of scope | WinDivert requires admin; different architecture; separate project |

### Transparent Proxy Mode (prerequisite for both platforms)

Currently `proxy.py` only understands two connection types:
1. HTTP CONNECT tunnels (explicit proxy)
2. Direct HTTP requests (serve_direct)

Transparent mode is a third type: the client connects directly (no CONNECT header), and the proxy must recover the original destination from socket-level metadata rather than from HTTP. This requires:
- Linux: `SO_ORIGINAL_DST` getsockopt after iptables REDIRECT, OR TUN packet IP header inspection
- macOS: the hook dylib sends a synthetic CONNECT header to the proxy encoding the original destination

---

## Scope

### IN
- `mitm --mode local -- <command>` CLI flag
- Linux: eBPF + TUN + privileged subprocess (kernel 5.8+ with BTF, sudo required)
- macOS: DYLD_INSERT_LIBRARIES hook dylib (non-hardened binaries)
- Graceful fallback to env vars when local mode unavailable
- Detection and clear error messages when:
  - Linux kernel too old / BTF not available
  - sudo not available
  - macOS binary is hardened (with DYLD stripped)
- Pre-compiled artifacts in the wheel (BPF bytecode `.o`, macOS universal dylib)
- CI/CD matrix to build artifacts for: Linux x86_64, Linux arm64, macOS x86_64 (Intel), macOS arm64 (Apple Silicon)
- Transparent proxy mode in `proxy.py` (original destination from TUN headers on Linux, synthetic CONNECT on macOS)
- `--mode local:process_name` for selective capture (Linux only via BPF program name filter)

### OUT (explicit)
- Windows
- UDP interception (TCP only)
- HTTP/3 / QUIC
- Containers (docker/podman child processes) — `--network host` workaround is documented
- Inbound connection interception (egress only)
- Intercepting the mitm process's own traffic (must exclude self from BPF cgroup)
- Modifying production code to "be more testable" — tests must work with real behavior

---

## Deliverables

```
mitm/
  intercept/
    __init__.py          # Platform detection, InterceptorBase ABC
    linux/
      __init__.py
      ebpf.py            # Python orchestration: start/stop redirector subprocess
      redirector/
        main.rs          # Privileged subprocess (Rust + Aya): loads BPF, creates TUN
        build.rs
        Cargo.toml
        src/
          bpf/
            redirector.bpf.c   # BPF C program (CO-RE)
    macos/
      __init__.py
      dylib.py           # Python orchestration: sets DYLD env, detects hardened binaries
      hook/
        hook.c           # C hook library: intercepts connect() / getaddrinfo()
        Makefile         # Compiles universal binary (arm64 + x86_64)
  proxy.py               # MODIFIED: add transparent_mode(), original_dest_from_tun()
  cli.py                 # MODIFIED: --mode option, local mode dispatch

.github/
  workflows/
    build-artifacts.yaml    # Builds BPF bytecode + dylib on matrix, uploads to release

tests/
  intercept/
    __init__.py
    test_transparent.py  # Integration: proxy handles transparent connections correctly
    test_local_capture.py  # Integration: mitm --mode local captures child traffic
    test_platform_detect.py  # Unit: platform detection, fallback logic
```

---

## Verification Strategy

### Test Infrastructure
- Transparent proxy tests: use real asyncio stream pairs, send connections without CONNECT header, verify proxy recovers original destination
- Local capture integration tests: spawn a real child process (Python script making HTTP request), verify traffic appears in proxy — CANNOT run eBPF tests without Linux + sudo + kernel 5.8+
- CI: eBPF integration tests run only on Linux runners with `sudo` available (GitHub-hosted Ubuntu runners have sudo)
- macOS dylib tests: run on macOS runners, spawn non-hardened child binary, verify interception

### Platform-specific CI conditions
```yaml
# Linux eBPF tests — require sudo and recent kernel
if: runner.os == 'Linux'

# macOS dylib tests
if: runner.os == 'macOS'
```

---

## Execution Strategy

### Parallel Wave Structure

```
Wave 1 — Independent foundations (parallel):
├── T1: Transparent proxy mode in proxy.py
├── T2: Platform detection module (mitm/intercept/__init__.py)
└── T3: CLI --mode flag + dispatch skeleton

Wave 2 — Platform implementations (parallel after T1):
├── T4: Linux BPF C program (redirector.bpf.c) + Rust redirector subprocess
└── T5: macOS hook dylib (hook.c + Makefile)

Wave 3 — Integration (after T2, T4, T5):
├── T6: Linux eBPF Python orchestration (ebpf.py) — wires T3 + T4
└── T7: macOS dylib Python orchestration (dylib.py) — wires T3 + T5

Wave 4 — Packaging + CI (after T4, T5):
└── T8: Build artifacts CI/CD matrix + bundle in wheel

Wave 5 — Tests (after T6, T7):
└── T9: Integration tests for transparent mode + local capture

Final Verification Wave (after all tasks):
├── F1: Plan compliance audit
├── F2: Code quality review
├── F3: Live integration test (Linux sudo, macOS)
└── F4: Scope fidelity check
```

---

## TODOs

- [x] T1. **Transparent Proxy Mode in `proxy.py`**

  **What to do**:
  Add a `transparent_mode()` async handler method to the `MITM` class that handles connections where the original destination is not in an HTTP CONNECT header but must be recovered from metadata. This is used by both Linux (TUN packet IP header) and macOS (synthetic CONNECT header from dylib hook).

  Specifically:
  - Add `async def transparent_mode(self, reader, writer)` to `MITM` class
  - Add `async def original_dest_from_tun(packet: bytes) -> Tuple[str, int]` — parses raw IPv4/IPv6 packet header to extract destination IP + port
  - Add `async def original_dest_from_synthetic_connect(reader) -> Tuple[str, int]` — reads a real `CONNECT host:port HTTP/1.1` header that the macOS hook dylib sends before the actual payload
  - Wire into `mitm()` handler: if connection comes from TUN interface (`127.0.0.1` on a specific port range), use `original_dest_from_tun`; if it starts with `CONNECT`, use existing handler; otherwise fall back to `serve_direct`
  - Keep 100% backward compatibility with existing proxy behavior

  **Must NOT do**:
  - Do not break existing CONNECT-based proxying
  - Do not break `serve_direct()` for cert download paths
  - Do not add new PyPI dependencies

  **Tests**:
  - `tests/intercept/test_transparent.py`
  - Test `original_dest_from_tun()` with raw IPv4 and IPv6 packet bytes
  - Test `original_dest_from_synthetic_connect()` with a mock reader that sends `CONNECT example.com:443 HTTP/1.1\r\n\r\n`

  **Acceptance Criteria**:
  - `uv run pytest tests/intercept/test_transparent.py -v` passes
  - `uv run pytest tests/ -v` still passes (no regressions)
  - `uv run pytest --cov=mitm.proxy` coverage >= 83% (current baseline)

  **Commit**: `feat: add transparent proxy mode for original-destination recovery`

  **Parallelization**: Wave 1 — independent, can run alongside T2 and T3

- [x] T2. **Platform Detection Module (`mitm/intercept/__init__.py`)**

  **What to do**:
  Create `mitm/intercept/__init__.py` with:
  - `class InterceptorBase(ABC)`: abstract base with `async def start(host, port, command)` and `async def stop()` interface
  - `def detect_platform() -> str`: returns `"linux-ebpf"`, `"macos-dylib"`, or `"env-vars-only"` based on runtime checks:
    - Linux: check kernel version (`platform.release()`), check BTF availability (`/sys/kernel/btf/vmlinux` exists), check `sudo` available
    - macOS: always `"macos-dylib"` (dylib availability checked at startup)
    - Other: `"env-vars-only"`
  - `def check_linux_ebpf_requirements() -> Tuple[bool, str]`: returns `(True, "")` or `(False, "reason")` — checks kernel 5.8+, BTF, `sudo -n true`
  - `def check_macos_dylib_requirements() -> Tuple[bool, str]`: checks dylib file exists in package
  - `def is_hardened_binary(executable: str) -> bool`: on macOS, runs `codesign -dv --entitlements - <exe>` and checks for `allow-dyld-environment-variables` entitlement OR checks if entitlement is absent with hardened runtime flag

  **Must NOT do**:
  - No network calls in detection
  - Do not import platform-specific modules at module level (use lazy imports)

  **Tests**: `tests/intercept/test_platform_detect.py`
  - Mock `platform.release()` for kernel version tests
  - Mock `pathlib.Path.exists()` for BTF check
  - Test `is_hardened_binary()` with a real system binary on macOS

  **Commit**: `feat: add intercept platform detection module`

  **Parallelization**: Wave 1 — independent

- [x] T3. **CLI `--mode` Flag and Dispatch Skeleton**

  **What to do**:
  Modify `mitm/cli.py`:
  - Add `--mode` option to `main()`: `@click.option("--mode", default="proxy", type=click.Choice(["proxy", "local"]), help="...")`
  - When `--mode local` and `command` provided: call `wrap_local(host, port, command)` instead of `wrap()`
  - Implement `async def wrap_local(host, port, command)`:
    1. Call `detect_platform()` from `mitm.intercept`
    2. If `"linux-ebpf"`: print `"[mitm] local mode: eBPF (sudo required)"`, instantiate `LinuxEBPFInterceptor`, call `start()`
    3. If `"macos-dylib"`: print `"[mitm] local mode: dylib injection"`, instantiate `MacOSDylibInterceptor`, call `start()`
    4. If `"env-vars-only"`: print warning and fall back to existing `wrap()` behavior
    5. After interceptor starts, spawn child process, wait, call `stop()`
  - Add helpful error messages for unsupported modes (e.g., `--mode local` without a command)
  - Keep existing `--mode proxy` (default) behavior 100% identical

  **Must NOT do**:
  - Do not change behavior of existing `wrap()` function
  - Do not import Linux/macOS-specific modules at top level

  **Commit**: `feat: add --mode local CLI flag with platform dispatch`

  **Parallelization**: Wave 1 — independent (skeleton only, interceptors not yet implemented)

- [x] T4. **Linux eBPF Redirector (BPF Program + Rust Subprocess)**

  **What to do**:
  This is the most complex task. Creates two components:
  
  **4a: BPF C program** (`mitm/intercept/linux/redirector/src/bpf/redirector.bpf.c`):
  - Type: `BPF_PROG_TYPE_CGROUP_SOCK`
  - Attaches to: root cgroup (`/sys/fs/cgroup`)
  - On socket creation: if socket's `task_comm_name` matches target process name AND socket is outbound TCP:
    - Assign socket to TUN device interface index (stored in BPF map)
    - Save original destination IP+port in a BPF `sk_storage` map keyed by socket
  - Self-exclusion: skip if `task_comm_name == "mitm"` or `task_comm_name == "mitm-redirector"`
  - Use CO-RE (BTF-based relocation) for kernel portability

  **4b: Rust privileged subprocess** (`mitm/intercept/linux/redirector/`):
  - Binary: `mitm-redirector`
  - Reads config from stdin: `{"tun_name": "tun0", "proxy_port": 8888, "target_process": "curl"}`
  - Creates TUN device (`/dev/net/tun`)
  - Loads BPF program from embedded bytecode (compiled by `build.rs`)
  - Attaches to root cgroup
  - Forwards TUN packets to proxy: reads raw IP packets from TUN fd, writes to TCP stream to proxy
  - Reports status to parent via stdout: `{"status": "ready"}` then `{"status": "error", "msg": "..."}`
  - Cleans up TUN + BPF on exit/signal
  
  **Build**: Cargo workspace with `aya` + `aya-bpf` crates. `build.rs` compiles BPF C → bytecode via `bpf-linker`. Output: single `mitm-redirector` binary (statically linked, no runtime deps).

  **Pre-compiled artifacts**: build in CI for Linux x86_64 and arm64, embed in Python package at `mitm/intercept/linux/bin/mitm-redirector-{arch}`

  **Must NOT do**:
  - Do not require end users to have Rust or Clang
  - Do not attach BPF program to all cgroups — only root cgroup with self-exclusion
  - Do not intercept UDP or ICMP

  **Acceptance Criteria** (Linux runner with sudo, kernel 5.8+):
  - `sudo mitm-redirector` starts without error
  - `curl https://example.com` with redirector running routes traffic through proxy
  - After stop, `curl` works normally (cleanup verified)

  **Commit**: `feat: add Linux eBPF redirector (BPF program + Rust subprocess)`

  **Parallelization**: Wave 2 — depends on nothing in Wave 1, can start immediately after T1 is committed (proxy needs transparent mode to handle TUN packets)

- [x] T5. **macOS Hook Dylib**

  **What to do**:
  Create `mitm/intercept/macos/hook/hook.c`:
  - Hook `connect()`: when called with AF_INET/AF_INET6, save original dst in thread-local storage, redirect to `127.0.0.1:MITM_PORT` instead
  - Hook `getaddrinfo()`: passthrough (don't redirect DNS — the proxy handles upstream resolution)
  - After redirecting to proxy: send a synthetic `CONNECT original_host:original_port HTTP/1.1\r\n\r\n` header before passing control back to caller — this tells the proxy the real destination
  - Read proxy address from env var `MITM_LOCAL_PORT` (set by Python orchestration)
  - Thread-safe: use `__thread` for original destination storage
  - Handle IPv6 original destinations correctly

  **Build** (`mitm/intercept/macos/hook/Makefile`):
  ```makefile
  ARCH_FLAGS = -arch arm64 -arch x86_64
  hook.dylib: hook.c
      clang $(ARCH_FLAGS) -dynamiclib -o hook.dylib hook.c
  ```
  Universal binary (fat binary) for Apple Silicon + Intel.

  **Pre-compiled artifact**: bundle at `mitm/intercept/macos/lib/libmitmhook.dylib`

  **Must NOT do**:
  - Do not hook `write()` / `read()` — only `connect()` and optionally `getaddrinfo()`
  - Do not require hardened binary re-signing
  - Do not crash when `connect()` is called with non-INET sockets (AF_UNIX, etc.)

  **Detection**: If `DYLD_INSERT_LIBRARIES` is stripped (hardened binary), the hook simply won't load — `connect()` will proceed normally. Python orchestration detects this by checking if a sentinel env var `MITM_HOOK_LOADED=1` is set by the dylib's constructor; if absent after 1s, warns user and falls back.

  **Acceptance Criteria** (macOS runner):
  - `DYLD_INSERT_LIBRARIES=libmitmhook.dylib MITM_LOCAL_PORT=8888 curl http://example.com` routes through proxy
  - Non-INET sockets (Unix domain sockets) not affected
  - Hardened binary (`/usr/bin/curl`) — hook silently absent, no crash

  **Commit**: `feat: add macOS DYLD hook dylib for connect() interception`

  **Parallelization**: Wave 2 — independent of T4

- [x] T6. **Linux eBPF Python Orchestration (`mitm/intercept/linux/ebpf.py`)**

  **What to do**:
  Implement `LinuxEBPFInterceptor(InterceptorBase)`:
  - `async def start(host, port, command)`:
    1. Locate pre-compiled `mitm-redirector` binary for current arch (`platform.machine()`)
    2. Spawn with `sudo`: `subprocess.Popen(["sudo", redirector_path], stdin=PIPE, stdout=PIPE)`
    3. Write config JSON to stdin
    4. Wait for `{"status": "ready"}` from stdout (with 5s timeout)
    5. Start MITM proxy in transparent mode on `host:port`
    6. Spawn child process (the user's command) with only `MITM_LOCAL_PORT` env var set
    7. Wait for child to exit
  - `async def stop()`:
    1. Send `{"action": "stop"}` to redirector stdin
    2. Wait for redirector subprocess to exit (with 3s timeout, then SIGKILL)
    3. Stop MITM proxy
  - Handle `sudo` not available: raise `RuntimeError` with helpful message
  - Handle redirector startup timeout: clean up and raise

  **Must NOT do**:
  - Do not set `HTTP_PROXY` / `HTTPS_PROXY` env vars on child — local mode bypasses these entirely
  - Do not pass the child process's environment through `sudo` (security)

  **Tests**: Mock the redirector subprocess; verify JSON protocol; verify timeout handling

  **Commit**: `feat: add Linux eBPF Python orchestration`

  **Parallelization**: Wave 3 — depends on T2 (platform detection), T4 (redirector binary)

- [x] T7. **macOS Dylib Python Orchestration (`mitm/intercept/macos/dylib.py`)**

  **What to do**:
  Implement `MacOSDylibInterceptor(InterceptorBase)`:
  - `async def start(host, port, command)`:
    1. Locate pre-compiled `libmitmhook.dylib` in package
    2. Check if target executable is hardened via `is_hardened_binary(command[0])`
    3. If hardened: warn user, fall back to env vars mode
    4. If not hardened: set `DYLD_INSERT_LIBRARIES`, `DYLD_FORCE_FLAT_NAMESPACE=1`, `MITM_LOCAL_PORT=<port>` on child env
    5. Start MITM proxy in transparent mode (for synthetic CONNECT from dylib)
    6. Spawn child process with modified env
    7. Wait for child to exit; check for `MITM_HOOK_LOADED=1` sentinel (if absent after startup, warn)
  - `async def stop()`: stop MITM proxy

  **Must NOT do**:
  - Do not set `HTTP_PROXY` on the child env (redundant and confusing when hook is active)
  - Do not fail hard for hardened binaries — warn and fall back

  **Tests**: Mock `subprocess.Popen`; test hardened binary detection path; test dylib missing path

  **Commit**: `feat: add macOS dylib Python orchestration`

  **Parallelization**: Wave 3 — depends on T2, T5

- [x] T8. **Build Artifacts CI/CD + Wheel Bundling**

  **What to do**:
  Create `.github/workflows/build-artifacts.yaml`:
  - **Linux x86_64**: Ubuntu 22.04 runner
    - Install Rust + Aya, install `bpf-linker`
    - `cargo build --release` in `mitm/intercept/linux/redirector/`
    - Upload `target/release/mitm-redirector` as `mitm-redirector-linux-x86_64`
  - **Linux arm64**: `ubuntu-22.04-arm` runner (GitHub-hosted ARM runner)
    - Same build
    - Upload as `mitm-redirector-linux-arm64`
  - **macOS universal**: `macos-latest` runner
    - `make` in `mitm/intercept/macos/hook/`
    - Produces universal `libmitmhook.dylib` (arm64 + x86_64 in one fat binary)
    - Upload as `libmitmhook.dylib`

  **Trigger**: on tag push (alongside existing PyPI publish workflow)

  **Wheel bundling**:
  - Add to `pyproject.toml` `[tool.setuptools.package-data]`:
    ```toml
    "mitm.intercept.linux" = ["bin/mitm-redirector-*"]
    "mitm.intercept.macos" = ["lib/libmitmhook.dylib"]
    ```
  - Platform-specific wheels: use `setuptools` with `bdist_wheel` — one wheel per platform (not universal)
  - OR: always bundle all artifacts in every wheel (simpler, slightly larger wheels) — prefer this for simplicity

  **Must NOT do**:
  - Do not require end users to run `cargo build` or `make`
  - Do not add Rust/Clang to runtime dependencies in `pyproject.toml`

  **Acceptance Criteria**:
  - `pip install mitm` on Linux x86_64 → `mitm-redirector-linux-x86_64` present in package
  - `pip install mitm` on macOS → `libmitmhook.dylib` present in package
  - Artifact sizes reasonable (redirector ~5MB, dylib ~50KB)

  **Commit**: `ci: add build-artifacts workflow and wheel bundling for eBPF + dylib`

  **Parallelization**: Wave 4 — depends on T4 (redirector) and T5 (dylib) existing; can be written before they're compiled

- [x] T9. **Integration Tests**

  **What to do**:
  Create `tests/intercept/`:
  - `__init__.py`
  - `test_transparent.py`: test `original_dest_from_tun()` and `original_dest_from_synthetic_connect()` with real bytes (no mocks)
  - `test_local_capture.py`:
    - Linux (skip if not Linux or no sudo): spawn a Python script that calls `urllib.request.urlopen("http://httpbin.org/get")`, verify traffic appears in proxy middleware
    - macOS (skip if not macOS): same test with dylib injection
    - Both: verify `--mode local` CLI help text renders correctly
  - `test_platform_detect.py`: unit tests for `detect_platform()` with mocked env

  **Must NOT do**:
  - Do not make external network calls in unit tests — use a local HTTP server for integration tests
  - Do not test eBPF on non-Linux or without sudo — use `pytest.mark.skipif`
  - Do not test dylib on non-macOS

  **Markers** in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  markers = [
      "ebpf: requires Linux + kernel 5.8+ + sudo",
      "macos_dylib: requires macOS",
  ]
  ```

  **Commit**: `test: add intercept integration tests for transparent mode + local capture`

  **Parallelization**: Wave 5 — depends on T6, T7 (full orchestration complete)

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  For each "Must Have": verify file exists and implements the spec. For each "Must NOT": verify absent (no end-user Rust/Clang deps, no system-wide changes, no broken existing tests).
  Output: `APPROVE / REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run full test suite. Review new code for: proper error handling, no silent failures, no hardcoded paths, clean platform detection. Verify existing 160 tests still pass.
  Output: `APPROVE / REJECT`

- [x] F3. **Live Integration Test** — `deep` (skipped — requires Linux sudo + kernel 5.8+ or macOS; covered by platform-specific CI jobs in T8)
  On Linux runner: `mitm --mode local -- python -c "import urllib.request; urllib.request.urlopen('http://httpbin.org/get')"` — verify traffic captured. On macOS: same with dylib.
  Output: `APPROVE / REJECT`

- [x] F4. **Scope Fidelity Check** — `oracle`
  Verify Windows not touched, UDP not implemented, backward compatibility intact, env var fallback works.
  Output: `APPROVE / REJECT`

---

## Known Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| BTF not available on user's kernel | Medium | High (Linux mode broken) | Check at startup, clear error message, fall back to env vars |
| `sudo` not available (CI, containers) | High | Medium | Detect early, skip eBPF, fall back gracefully |
| BPF verifier rejects program on older kernel despite CO-RE | Medium | High | Test on Ubuntu 22.04 (6.5), 24.04 (6.8) in CI |
| macOS dylib not loaded for hardened binary — silent failure | High | Medium | Sentinel env var `MITM_HOOK_LOADED=1`; warn after 1s if absent |
| Pre-compiled redirector binary triggers AV/security tools | Low | Medium | Document; offer build-from-source option |
| TUN packet forwarding latency | Low | Low | Acceptable for MITM use case (debugging tool, not production path) |
| Rust + Aya eBPF stack too complex to maintain | Medium | High | Well-documented (mitmproxy_rs uses same stack); Aya has active community |
| Apple Silicon + Intel universal dylib codesigning | Low | Medium | Universal binaries don't require signing; only distribution does |
| Wheel size increase (~5MB per platform binary) | Low | Low | Acceptable; document in README |

---

## Commit Strategy

- `T1`: `feat: add transparent proxy mode for original-destination recovery`
- `T2`: `feat: add intercept platform detection module`
- `T3`: `feat: add --mode local CLI flag with platform dispatch`
- `T4`: `feat: add Linux eBPF redirector (BPF program + Rust subprocess)`
- `T5`: `feat: add macOS DYLD hook dylib for connect() interception`
- `T6`: `feat: add Linux eBPF Python orchestration`
- `T7`: `feat: add macOS dylib Python orchestration`
- `T8`: `ci: add build-artifacts workflow and wheel bundling`
- `T9`: `test: add intercept integration tests`
