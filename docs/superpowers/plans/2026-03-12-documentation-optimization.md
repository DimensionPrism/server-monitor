# Documentation Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repo’s top-level documentation operator-clear and release-consistent without rewriting the dated engineering archive.

**Architecture:** Treat `README.md` as the canonical current-state/operator document, `docs/roadmap-v1-future-path.md` as the canonical release-history and future-roadmap document, and the dated spec/plan files as archive records. Add one tiny docs index so readers opening `docs/` directly can find the right entry points immediately.

**Tech Stack:** Markdown, TOML comments, ripgrep, git diff.

---

## File Structure

- Modify: `README.md`
  - Tighten current-state/operator wording, especially stream-versus-poll semantics and doc navigation.
- Modify: `docs/roadmap-v1-future-path.md`
  - Add explicit `v1.3` shipped status, release mapping notes, and contiguous sequencing.
- Create: `docs/README.md`
  - Provide a minimal docs navigation/index page.
- Modify: `config/servers.example.toml`
  - Keep the `metrics_interval_seconds` comment concise and operator-focused.
- Modify: `config/local-dashboard.example.toml`
  - Keep the `metrics_interval_seconds` comment concise and operator-focused.

## Chunk 1: Canonical Operator Docs

### Task 1: Tighten `README.md` as the canonical current-state doc

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the failing verification criteria**

Define the exact conditions `README.md` must satisfy after the edit:

- it clearly states `system`/`gpu` are streamed
- it clearly states `git`/`clash` are polled
- it links readers to the roadmap/history docs
- it does not describe `system`/`gpu` as normal batched polling

Write those checks down in the working notes for this task before editing.

- [ ] **Step 2: Run a baseline grep to capture the current wording**

Run:

```bash
rg -n "system|gpu|git|clash|stream|poll|roadmap|history" README.md
```

Expected: current wording is visible, including any remaining mixed transport language.

- [ ] **Step 3: Edit `README.md` minimally**

Update `README.md` so it:

- presents the stream/poll split cleanly
- keeps setup/run/testing intact
- adds a short “where to read more” pointer to roadmap/history docs
- avoids duplicating detailed release-history content

- [ ] **Step 4: Re-run the grep check**

Run:

```bash
rg -n "system|gpu|git|clash|stream|poll|roadmap|history" README.md
```

Expected: streamed versus polled responsibilities are explicit and no stale `system`/`gpu` polling wording remains.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: tighten operator readme"
```

## Chunk 2: Release History and Docs Navigation

### Task 2: Repair roadmap release history and version mapping

**Files:**
- Modify: `docs/roadmap-v1-future-path.md`

- [ ] **Step 1: Write the failing verification criteria**

Define the exact conditions the roadmap must satisfy:

- explicit `v1.3 Status`
- explicit `v1.4 Status`
- clear mapping note for `v13` -> `v1.3` and `v14` -> `v1.4`
- contiguous release sequencing with future work moved after shipped work

- [ ] **Step 2: Inspect the current roadmap sections**

Run:

```bash
rg -n "^## |^1\\.|^2\\.|^3\\.|^4\\.|^5\\." docs/roadmap-v1-future-path.md
```

Expected: current release-history gap is visible.

- [ ] **Step 3: Edit the roadmap**

Update `docs/roadmap-v1-future-path.md` to:

- add `v1.3 Status`
- retain `v1.4 Status`
- add a short note explaining the engineering archive naming shorthand
- keep future work as future work

- [ ] **Step 4: Re-run the roadmap structure grep**

Run:

```bash
rg -n "^## |v1\\.3|v1\\.4|v1\\.5|v13|v14" docs/roadmap-v1-future-path.md
```

Expected: `v1.3`, `v1.4`, and the mapping note are now explicit.

- [ ] **Step 5: Commit**

```bash
git add docs/roadmap-v1-future-path.md
git commit -m "docs: clarify release history and version mapping"
```

### Task 3: Add a small docs index

**Files:**
- Create: `docs/README.md`

- [ ] **Step 1: Write the failing verification criteria**

Define the exact conditions the docs index must satisfy:

- tell readers where to start
- point to `README.md` for current operator behavior
- point to the roadmap for release history
- describe `docs/superpowers/specs/*` and `docs/superpowers/plans/*` as archive records

- [ ] **Step 2: Confirm there is no existing docs index**

Run:

```bash
dir docs
```

Expected: no current `docs/README.md` or equivalent canonical docs entry point exists.

- [ ] **Step 3: Create `docs/README.md`**

Write a short index with sections like:

- Start Here
- Release History and Roadmap
- Engineering Archive

Keep it brief and link-focused.

- [ ] **Step 4: Inspect the new file**

Run:

```bash
Get-Content docs/README.md
```

Expected: concise navigation doc with the right pointers and role boundaries.

- [ ] **Step 5: Commit**

```bash
git add docs/README.md
git commit -m "docs: add top-level docs index"
```

## Chunk 3: Example Config Guidance and Verification

### Task 4: Keep example config semantics clear

**Files:**
- Modify: `config/servers.example.toml`
- Modify: `config/local-dashboard.example.toml`

- [ ] **Step 1: Write the failing verification criteria**

Define the exact conditions the example config comments must satisfy:

- explain `metrics_interval_seconds` no longer controls streamed `system`/`gpu` cadence
- remain short and operator-focused
- avoid turning example configs into prose-heavy docs

- [ ] **Step 2: Inspect the current comments**

Run:

```bash
Get-Content config/servers.example.toml
Get-Content config/local-dashboard.example.toml
```

Expected: current comments are visible for review.

- [ ] **Step 3: Edit only if needed**

If the comments are already correct and concise, leave them unchanged and record that no edit was needed. If they need tightening, update them minimally.

- [ ] **Step 4: Re-check the top of both files**

Run:

```bash
Get-Content config/servers.example.toml -TotalCount 5
Get-Content config/local-dashboard.example.toml -TotalCount 5
```

Expected: the comments are short, accurate, and consistent.

- [ ] **Step 5: Commit**

```bash
git add config/servers.example.toml config/local-dashboard.example.toml
git commit -m "docs: clarify example config streaming semantics"
```

### Task 5: Run docs verification and finalize

**Files:**
- Modify: `README.md`
- Modify: `docs/roadmap-v1-future-path.md`
- Create or Modify: `docs/README.md`
- Modify: `config/servers.example.toml`
- Modify: `config/local-dashboard.example.toml`

- [ ] **Step 1: Inspect the final diff**

Run:

```bash
git diff -- README.md docs/roadmap-v1-future-path.md docs/README.md config/servers.example.toml config/local-dashboard.example.toml
```

Expected: only the agreed documentation files changed, and the edits stay operator-first.

- [ ] **Step 2: Run consistency grep checks**

Run:

```bash
rg -n "v1\\.3|v1\\.4|v1\\.5|v13|v14|stream|poll|metrics_interval_seconds" README.md docs/README.md docs/roadmap-v1-future-path.md config/servers.example.toml config/local-dashboard.example.toml
```

Expected: the top-level docs consistently describe the current architecture and release mapping.

- [ ] **Step 3: Verify working tree cleanliness apart from unrelated existing files**

Run:

```bash
git status --short --branch
```

Expected: only the intended documentation files are staged or committed; unrelated pre-existing untracked docs remain untouched.

- [ ] **Step 4: Commit the final combined doc cleanup if needed**

If earlier tasks left uncommitted documentation changes:

```bash
git add README.md docs/roadmap-v1-future-path.md docs/README.md config/servers.example.toml config/local-dashboard.example.toml
git commit -m "docs: optimize top-level documentation"
```

If everything is already committed task-by-task, skip this step.

- [ ] **Step 5: Report completion**

Summarize:

- what changed in operator docs
- how release-history ambiguity was resolved
- that the archive docs were intentionally left untouched
