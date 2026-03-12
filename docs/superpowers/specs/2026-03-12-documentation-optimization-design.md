# Documentation Optimization Design

## Summary

The repository documentation should be optimized for two goals:

1. make the current product behavior easy for operators and new contributors to understand
2. preserve the existing dated engineering specs and plans as historical archive records

The immediate problem is not that the repo lacks documentation. It is that the current documentation surface does not make roles and authority clear enough:

- `README.md` mixes current operator guidance with some older transport wording
- `docs/roadmap-v1-future-path.md` is the obvious place to understand release progression, but it currently skips an explicit `v1.3` release status section even though `v1.3` transport-latency work was implemented
- the `docs/superpowers/specs/*` and `docs/superpowers/plans/*` archive is useful, but a reader can mistake those dated documents for the current source of truth if top-level docs are not sharper

The design should therefore optimize the top-level docs while leaving the archive intact.

## Goals

- Make `README.md` the canonical operator-facing entry point
- Make `docs/roadmap-v1-future-path.md` the canonical release-history and forward-roadmap document
- Make it obvious that dated specs and plans are engineering archive records, not the primary description of current behavior
- Resolve the `v1.3` versus `v13` naming confusion without renaming historical files
- Keep the cleanup small, focused, and low-risk

## Non-Goals

- Rewriting the historical spec and plan archive
- Renaming dated spec or plan files
- Creating a full documentation site or heavy documentation IA system
- Backfilling every old historical doc to align perfectly with current runtime behavior

## Current Problems

### Operator Clarity

Operators should be able to answer these questions quickly:

- what runs as a stream versus a poll?
- what settings still matter after metrics streaming shipped?
- how do I verify the dashboard is healthy?

The current `README.md` already contains most of this information, but it still needs to be treated consistently as the canonical current-state document.

### Release-History Clarity

The roadmap currently has explicit status sections for `v1.1`, `v1.2`, and `v1.4`, but not `v1.3`.

That creates confusion because:

- the archive contains `v1.3 Dashboard Transport Latency` design and plan docs
- `main` includes the corresponding merged work (`feat: reduce dashboard polling latency`)
- a reader looking only at the roadmap can incorrectly conclude that `v1.3` never shipped

### Archive Boundaries

The dated spec and plan files are valuable engineering artifacts, but they should be treated as:

- design history
- execution history
- reasoning archive

They should not be treated as the first document someone reads to learn how the dashboard behaves today.

## Documentation Roles

### `README.md`

`README.md` should be the canonical operator and current-state document.

It should answer:

- what the dashboard does now
- high-level architecture at a glance
- how to run it
- which settings matter
- how to verify health and diagnose issues
- where to find roadmap/history docs

It should avoid stale phrasing that reintroduces previous architecture assumptions.

### `docs/roadmap-v1-future-path.md`

This should be the canonical release-history and forward-plan document.

It should answer:

- what shipped in each release
- what milestone names map to which release labels
- what remains future work
- what the current sequencing is

It should explicitly include `v1.3` and `v1.4` shipped status sections and keep sequencing contiguous.

### `docs/README.md` or `docs/index.md`

The `docs/` folder should have a tiny index document that explains how to navigate the docs surface.

It should point readers to:

- `README.md` for current operator guidance
- `docs/roadmap-v1-future-path.md` for release history and roadmap
- `docs/superpowers/specs/*` and `docs/superpowers/plans/*` for engineering archive records

This gives the repository a stable entry point for anyone who opens `docs/` directly.

### `docs/superpowers/specs/*` and `docs/superpowers/plans/*`

These remain unchanged in role.

They are archive records of:

- design intent at a point in time
- implementation planning at a point in time

They should not be renamed or rewritten during this cleanup.

## Versioning and Naming Design

The cleanup should make one rule explicit:

- release labels use `v1.x`
- dated engineering filenames may include shorthand milestone labels like `v13` or `v14`
- those milestone labels map to release labels and are not a separate numbering system

The roadmap should explicitly document that:

- `2026-03-12-v13-dashboard-transport-latency-*` corresponds to release `v1.3`
- `2026-03-12-v14-agentless-metrics-streaming-*` corresponds to release `v1.4`

This resolves the naming confusion without disturbing the archive.

## Recommended Cleanup Scope

### 1. Tighten `README.md`

Update `README.md` so it reads as a clean current-state operator document:

- keep “What Works Now”
- keep setup and run sections
- keep key operational notes
- keep testing commands
- add or tighten links to roadmap/history docs
- remove duplicated or legacy wording that can blur the stream-versus-poll boundary

### 2. Repair the Roadmap

Update `docs/roadmap-v1-future-path.md` to:

- add a `v1.3 Status` section
- keep the `v1.4 Status` section
- add a short release-mapping note that explains `v13`/`v14` archive naming
- make release sequencing contiguous

### 3. Add a Small Docs Index

Add a lightweight `docs/README.md` or `docs/index.md` that states:

- where to start
- what each top-level doc is for
- what the dated archive contains

This is enough structure without overbuilding a documentation system.

### 4. Keep Example Config Docs Short

Retain short comments in `config/servers.example.toml` and `config/local-dashboard.example.toml` for settings that changed meaning after streaming shipped.

These comments should stay minimal and operator-focused.

## Testing and Verification

This is a docs-only cleanup, so verification should focus on correctness and consistency rather than runtime behavior.

Verification should include:

- inspect diffs for the touched docs
- grep for stale top-level wording that still describes `system`/`gpu` as normal polling
- confirm the roadmap explicitly includes `v1.3` and `v1.4`
- confirm the new docs index points to the right documents

No code or UI tests are required unless documentation changes accidentally touch executable files.

## Risks

### Risk: Over-editing Historical Docs

If the cleanup starts modifying dated spec and plan files, the archive becomes less trustworthy as a historical record.

Mitigation:

- treat historical docs as read-only archive for this pass
- fix discoverability and role boundaries in top-level docs instead

### Risk: Repeating Information Across Too Many Docs

If `README`, roadmap, docs index, and archive all try to explain current behavior in full, drift will happen again.

Mitigation:

- `README` owns current operator behavior
- roadmap owns release history and future sequencing
- docs index owns navigation only
- archive owns historical design/planning context

## Implementation Outline

1. update `README.md` for clearer operator-first structure and links
2. update `docs/roadmap-v1-future-path.md` to include `v1.3` status and release mapping notes
3. add a small `docs/README.md` or `docs/index.md`
4. verify the touched docs for consistency

This keeps the documentation optimization small, high-signal, and easy to maintain.
