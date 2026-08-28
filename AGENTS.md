# AGENTS.md — AiDM Codex Rules

## Role

Codex is the implementation agent for AiDM.

Architecture, feature design, scope decisions, and development priorities are decided outside Codex.

Codex must implement only the task explicitly provided in the current prompt.

Codex is not authorized to redesign the project, expand feature scope, or make unrelated improvements on its own.

---

## Core Rule

**Do only what was explicitly requested.**

If a requested task can be completed without changing unrelated code, unrelated code must remain untouched.

Do not perform opportunistic refactoring, cleanup, renaming, optimization, restructuring, or feature additions unless the prompt specifically requests them.

---

## Repository Awareness

Before editing code:

1. Inspect the files directly relevant to the requested task.
2. Understand the existing routing and architecture.
3. Reuse existing helpers and patterns where appropriate.
4. Preserve existing working behavior unless the prompt explicitly requests a change.

Do not assume behavior from another Git branch should be copied into the current branch unless explicitly instructed.

---

## Branch Isolation

AiDM uses separate Git branches to develop independent features.

Features developed in separate branches may later be merged.

Therefore:

* Keep branch-specific features architecturally isolated.
* Do not unnecessarily couple a new feature to unrelated functionality.
* Do not copy logic from another branch unless explicitly requested.
* Prefer clear feature-specific functions and routing over generic abstractions that combine unrelated features prematurely.

For the `bulk-direct-downloads` branch specifically:

**Direct bulk downloading and YouTube bulk downloading are separate features.**

Direct bulk belongs to the direct-download path handled by aria2c.

YouTube bulk belongs to the YouTube-specific path handled primarily by yt-dlp.

Do not create a generic bulk-download system that mixes both features unless a future task explicitly requests such architecture.

---

## Existing Behavior Protection

Unless explicitly requested, preserve:

* single direct downloads
* YouTube routing
* HLS routing
* DASH routing
* VTT detection
* unknown/site URL handling
* existing downloader selection
* existing command-line behavior outside the requested feature

A new feature must not silently change unrelated existing behavior.

---

## Minimal Changes

Make the smallest reasonable change necessary to complete the task.

Prefer modifying existing appropriate modules over creating unnecessary files.

Do not introduce new dependencies unless explicitly approved.

Do not alter downloader tuning, command flags, detection heuristics, output naming, or other established behavior unless required by the requested task.

---

## No Unrequested Features

Do not add features merely because they appear useful.

Examples include:

* GUI functionality
* clipboard integration
* batch-file import
* retry managers
* download queues
* concurrency managers
* configuration systems
* new command-line flags
* logging frameworks
* progress abstractions
* automatic fallback systems

Such features require separate approval and separate tasks.

---

## Error Handling

When adding new behavior:

* fail clearly when input is unsupported;
* avoid silently routing unsupported input somewhere else;
* preserve existing return-code conventions where practical;
* provide concise user-facing errors.

Do not hide failures with broad exception handling.

---

## Code Style

Follow the existing project's coding style.

Prefer:

* clear function names;
* straightforward control flow;
* small focused functions;
* readable Python over clever abstractions.

Avoid premature architecture.

---

## Testing Responsibility

After making requested changes:

1. Inspect the resulting diff.
2. Verify that only expected files changed.
3. Check for obvious syntax or import errors.
4. Provide exact manual test commands relevant to the task.
5. Explain the expected behavior of each test.

Do not claim a test passed unless it was actually executed successfully.

Clearly distinguish:

* tests actually executed;
* checks performed by inspection;
* tests the user still needs to run manually.

---

## Git Rules

Codex must not:

* create commits;
* amend commits;
* push branches;
* merge branches;
* rebase branches;
* delete branches;
* change Git history;

unless the current prompt explicitly requests that Git operation.

The user controls commits and pushes.

---

## Completion Report

After each coding task, stop making changes and report:

1. Files changed.
2. What changed in each file.
3. Why each change was necessary.
4. Existing behavior intentionally preserved.
5. Tests/checks actually performed.
6. Exact manual test commands for the user.
7. Any known limitation directly relevant to the implemented task.

Do not continue into another feature without a new explicit instruction.

---

## Decision Escalation

If implementation reveals an architectural choice that was not specified in the task, do not independently make a large architectural decision.

Prefer the smallest behavior-preserving implementation possible and report the decision point.

Architecture decisions belong to the project owner and the ChatGPT planning workflow.

---

## Project Principle

AiDM development follows:

**small feature → test → verify → commit → next feature**

Do not combine multiple development milestones into one task unless explicitly requested.
