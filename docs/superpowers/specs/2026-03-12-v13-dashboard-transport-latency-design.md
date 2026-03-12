# v1.3 Dashboard Transport Latency Design

## Summary

The next backend optimization should reduce dashboard card latency without reducing freshness or removing card detail.

The current runtime is already correct at a functional level: it polls the right data, preserves cache state on transient failures, and exposes useful command-health diagnostics. The remaining latency is mostly transport cost from repeated one-shot SSH calls.

The design should therefore optimize transport in two stages:

1. batch multiple logical card polls into one SSH round trip per server and cadence
2. add a dashboard-managed persistent SSH session per alias so those batched polls stop paying repeated connection setup cost

This sequence matches the user request to do both while starting with the lower-risk piece first.

## Context and Constraints

### Current Poll Shape

With the current configuration:

- metrics poll every 1 second
- status panels poll every 10 seconds
- each server currently performs separate SSH invocations for:
  - `system`
  - `gpu`
  - each configured `git` repo
  - `clash` secret lookup
  - `clash` probe

Even after the git timeout fix, the dashboard is still paying SSH round-trip cost repeatedly.

### Platform Constraint

The local environment is running `OpenSSH_for_Windows_9.5p2`.

A live probe using `ControlMaster` and `ControlPersist` failed with:

- `getsockname failed: Not a socket`
- `Read from remote host ...: Unknown error`

That means the design must not depend on OpenSSH control sockets for the first or second milestone. If transport reuse is added, it must be managed by the dashboard process itself rather than delegated to OpenSSH multiplexing.

### Non-Negotiable Requirements

1. The dashboard must stay agentless.
2. Card freshness must stay the same.
3. Card detail must stay the same.
4. Existing dashboard payload shape for monitor data should stay stable.
5. Existing cache fallback semantics should stay intact.
6. Existing command-health diagnostics should remain useful after batching.
7. One logical card failure must not poison unrelated cards in the same batch.

## Scope

### In Scope

- Backend-only optimization for dashboard polling transport
- Batched metrics polling per server
- Batched status polling per server
- Batch protocol framing and parsing
- Persistent SSH session management inside the dashboard process
- Automatic fallback from persistent session to one-shot SSH
- Tests for batching, failure isolation, session restart, and diagnostics behavior
- README updates for the new transport behavior

### Out of Scope

- Remote agent deployment
- Changing metrics or status refresh intervals
- Reducing the amount of git or clash detail collected
- UI redesign
- Historical latency storage
- User-configurable transport tuning in this phase

## Requirements

1. Metrics polling must still deliver separate `system` and `gpu` card data on the existing cadence.
2. Status polling must still deliver separate git repo status and clash status on the existing cadence.
3. Batching must lower SSH round trips per server:
   - metrics: from two or more one-shot calls to one batched call
   - status: from multiple repo/clash calls to one batched call
4. Logical command results must remain independently classifiable for diagnostics:
   - success
   - timeout
   - ssh unreachable
   - non-zero exit
   - parse failure
   - cooldown skip
5. Existing last-known-good cache behavior must continue to work:
   - a failed repo keeps the previous repo snapshot
   - a failed clash probe keeps the previous clash snapshot
   - a failed batch does not erase last-good state
6. If the persistent session transport becomes unhealthy, the runtime must automatically fall back to one-shot SSH without operator intervention.
7. The optimization must preserve the current server configuration format in `config/servers.toml`.

## Proposed Module Boundaries

### `src/server_monitor/dashboard/runtime.py`

Remain the orchestration layer.

Responsibilities:

- decide when to run metrics and status polls
- call batched command builders instead of one logical SSH call per card
- unpack batch results back into logical command outcomes
- update caches, freshness, and command health
- choose transport fallback behavior

### `src/server_monitor/dashboard/batch_protocol.py`

New focused module for batch framing and parsing.

Responsibilities:

- build stable marker tokens
- parse section-delimited batch output
- expose a local representation for logical command sections
- validate malformed or truncated envelopes

This keeps batch parsing separate from runtime policy code.

### `src/server_monitor/dashboard/persistent_session.py`

New focused module for long-lived per-alias SSH sessions.

Responsibilities:

- start one `ssh <alias> sh` subprocess per alias on demand
- send sequential framed scripts through stdin
- read framed output until completion marker
- restart on timeout, EOF, or protocol corruption
- expose a `run(...)` shape that the runtime can use via the existing executor abstraction

### `src/server_monitor/dashboard/command_runner.py`

Keep the one-shot subprocess runner and provide the low-level primitives used by the persistent session module.

Responsibilities:

- one-shot command execution stays available as the fallback path
- persistent session code may reuse timeout and result-shaping helpers where it makes sense

## Stage 1: Batched Polling Design

### Metrics Batch

Replace separate `system` and `gpu` SSH invocations with one remote shell script per server.

The script should:

1. run the current system command
2. run the current GPU command
3. emit a section for each logical result with:
   - logical command kind
   - target label
   - exit code
   - duration metadata
   - stdout payload
   - stderr payload when relevant

The local runtime then parses the batch output and feeds the section payloads into the existing `parse_system_snapshot` and `parse_gpu_snapshot` functions.

### Status Batch

Replace per-repo git polling plus clash secret/probe calls with one remote shell script per server.

The script should:

1. emit one logical section per repo for `git status --porcelain --branch`
2. emit one logical section for the clash secret lookup
3. emit one logical section for the clash probe

This keeps the remote work the same while collapsing transport overhead.

### Batch Envelope

The batch protocol should use locally generated random marker tokens so raw command output is extremely unlikely to collide with framing markers.

Each logical result section should carry metadata in a header line, followed by raw payload, followed by an end marker. The parser must reject:

- missing end markers
- duplicated section identifiers
- malformed metadata
- truncated output

The protocol should prefer shell-only primitives and should not require Python on the remote host.

### Diagnostics Semantics

The dashboard must continue to show logical card latency, not only aggregate batch latency.

The preferred design is:

- each logical section carries its own duration metadata when available
- the runtime also records the outer batch duration for debugging

If a remote duration cannot be measured cleanly on a host, the runtime may fall back to the batch duration for that logical section rather than dropping latency reporting entirely.

## Stage 2: Persistent Session Design

### Transport Shape

After Stage 1 is stable, add a persistent per-alias SSH session managed by the dashboard process.

The session should:

- start lazily on first use
- execute one batched script at a time per alias
- remain alive across poll cycles
- be transparent to `DashboardRuntime`

Because the runtime already serializes execution per alias, the persistent session does not need concurrent in-flight request support in this phase.

### Framed Request/Response Model

Each request should be wrapped so the persistent session can detect completion and exit status without ambiguity.

The transport should:

- inject a per-request completion marker
- capture merged output for the request
- return a `CommandResult`-compatible object to the caller

Merged output is acceptable because the inner batch protocol already carries logical stdout, stderr, exit status, and duration per section.

### Recovery and Fallback

If the persistent session:

- times out
- exits unexpectedly
- returns malformed framing
- stops accepting input

then the runtime must:

1. kill and discard the session
2. mark the transport attempt as failed
3. rerun the same batched poll through the existing one-shot SSH path
4. allow a later poll to recreate the persistent session

This keeps the optimization safe: transport reuse is opportunistic, not required for correctness.

## Runtime Behavior Changes

### Metrics Poll Flow

The metrics cycle becomes:

1. build metrics batch script for one server
2. execute through the active transport
3. parse logical sections
4. update system and GPU cache entries independently
5. append logical command-health records for `system` and `gpu`

### Status Poll Flow

The status cycle becomes:

1. build status batch script for one server
2. execute through the active transport
3. parse logical sections
4. update repo cache per repo
5. update clash cache from secret/probe sections
6. append logical command-health records for each repo plus clash checks

### Failure Isolation

The runtime must treat each logical section independently after parsing the batch:

- one repo may fail while other repos succeed
- clash secret failure does not erase prior git results
- malformed whole-batch output fails the batch and preserves existing cache

## Testing Strategy

### Unit Tests

- batch protocol parsing with mixed success and failure sections
- malformed marker rejection
- empty payload handling
- persistent session restart on EOF or timeout
- persistent session fallback to one-shot execution

### Runtime Tests

- one executor call per server for metrics batching
- one executor call per server for status batching
- per-repo git failure isolation inside one status batch
- clash secret and probe behavior preserved under batching
- command-health summaries remain populated after batching

### Live Verification

After implementation:

1. run targeted pytest coverage for batch protocol, persistent session, and runtime integration
2. start the dashboard through `scripts/start-dashboard.ps1`
3. collect `/api/diagnostics` samples before and after the persistent-session milestone
4. confirm that:
   - card detail is unchanged
   - refresh cadence is unchanged
   - git/system/gpu/clash latencies are lower than the current one-shot baseline

## Risks and Mitigations

### Risk: Batch parsing becomes brittle

Mitigation:

- isolate protocol code in its own module
- use randomized framing markers
- add explicit malformed-envelope tests

### Risk: Persistent session state becomes stuck

Mitigation:

- allow only one in-flight request per alias
- kill and recreate the session on any framing or timeout error
- keep the one-shot SSH path as a first-class fallback

### Risk: Logical latency reporting becomes misleading

Mitigation:

- preserve per-logical-section duration when available
- keep outer batch duration available in diagnostics for comparison

## Recommendation

Implement the optimization in two milestones on the same branch:

1. batched metrics and status polling with logical result reconstruction
2. persistent per-alias SSH sessions with automatic fallback

This gives the biggest practical latency reduction available in the current Windows-hosted environment without changing dashboard freshness or detail.
