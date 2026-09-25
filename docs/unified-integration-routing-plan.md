# AiDM Unified Integration and Routing Plan

## Purpose

This document locks the engineering plan for integrating AiDM's currently separated feature branches before continuing deeper Stream Inspector integration.

The goal is to unify AiDM's routing intelligence in a dedicated integration branch while keeping `main` safe and preserving every proven feature branch as a known-good reference.

The integration work must prioritize routing correctness above local feature success. A new feature is not considered successful if it breaks an existing route.

---

## Core principle

AiDM should remain a low-friction terminal router.

The user should be able to run:

```text
python aidm.py [INPUT]
```

and AiDM should classify the input automatically and route it to the correct workflow.

The user should not need to select an engine manually or change command structure depending on whether the input is:

- a YouTube video;
- a YouTube playlist;
- multiple YouTube URLs;
- a direct HTTP/HTTPS file;
- multiple direct URLs;
- a local `.torrent` file;
- a naked HLS/DASH stream URL;
- a Stream Inspector handoff;
- or a generic website/media URL.

Classification and routing intelligence are therefore a core AiDM architectural responsibility.

---

## Hard boundary: existing feature intelligence must survive

The following feature branches contain working behavior that must not be lost during Stream Inspector development:

```text
feat/Streaming-URLs
feat/youtube
feat/bulk-direct-downloads
feat/2ndry-features
```

All of these branches are intended to contribute to the final AiDM architecture.

Changes made for streaming integration must not break or silently replace:

- YouTube single-video routing;
- YouTube playlist routing;
- YouTube bulk routing;
- direct-file routing;
- direct bulk sequential mode;
- direct bulk parallel mode;
- torrent routing;
- naked HLS/DASH routing;
- generic yt-dlp fallback behavior.

Routing integrity is part of the definition of success for every later milestone.

---

## Why integration happens before further Stream Inspector work

AiDM's routing intelligence is currently distributed across branches.

For example:

- `feat/youtube` contains playlist detection, YouTube URL normalization, and bulk YouTube behavior;
- `feat/bulk-direct-downloads` contains multi-direct-URL classification and sequential/parallel routing;
- `feat/2ndry-features` contains torrent-path detection and torrent routing;
- `feat/Streaming-URLs` contains the current streaming-specific work.

Continuing major Stream Inspector development only inside `feat/Streaming-URLs` would make later merging harder and would test the new streaming path against only a partial router.

Therefore the existing feature intelligence will first be unified in a dedicated integration branch.

---

## Branch strategy

### Main branch

`main` remains the protected known-good baseline during integration.

No experimental multi-branch integration should be performed directly on `main`.

### Feature branches

The existing feature branches remain preserved after merge.

They act as known-good references and recovery points.

If a capability breaks in the integration branch, its original feature branch can be inspected and compared directly.

Examples:

```text
YouTube regression
→ compare against feat/youtube

Direct bulk regression
→ compare against feat/bulk-direct-downloads

Torrent regression
→ compare against feat/2ndry-features

Streaming regression
→ compare against feat/Streaming-URLs
```

Feature branches should not be deleted merely because they have been merged into the integration branch.

### Integration branch

A new branch should be created from `main`.

Recommended name:

```text
integration/aidm-unified-router
```

This branch becomes the active development branch after the initial branch-unification phase.

Its purpose is:

1. combine all proven feature intelligence;
2. resolve routing conflicts deliberately;
3. establish one unified AiDM gate;
4. serve as the base for continued Stream Inspector integration;
5. protect `main` until the unified system is fully tested.

---

## Integration architecture

The intended high-level flow is:

```text
                       python aidm.py [INPUT]
                                │
                                ▼
                           AiDM input gate
                                │
                         classify the input
                                │
        ┌───────────────────────┼────────────────────────┐
        │                       │                        │
        ▼                       ▼                        ▼
     YouTube                  Direct                  Torrent
        │                       │                        │
     yt-dlp                  aria2c                   aria2c
        │
     aria2c
        │
     FFmpeg
   when required

                                │
                                ▼
                            Streaming
                                │
                     naked URL or Inspector
                                │
                              yt-dlp
                                │
                     browser context when supplied
```

The exact implementation structure may evolve, but the behavioral contract is fixed.

---

## Routing precedence

Specific and deterministic classifiers should run before broad fallback behavior.

The eventual routing logic should preserve the following conceptual precedence.

### Local torrent input

A local `.torrent` path must be recognized before HTTP/HTTPS-only validation rejects it.

Expected route:

```text
local .torrent
→ torrent classifier
→ aria2c
```

### Multiple positional inputs

Multiple inputs must be classified as a group.

Expected categories include:

```text
all YouTube URLs
→ YouTube bulk workflow

all direct URLs
→ direct bulk workflow

unsupported mixed batch
→ clear error
```

Multiple positional inputs must never be assumed to be direct downloads merely because there is more than one value.

### Single YouTube playlist

Expected route:

```text
YouTube playlist
→ playlist classifier
→ YouTube playlist workflow
```

### Single YouTube video

Expected route:

```text
YouTube video
→ YouTube classifier
→ yt-dlp
→ aria2c where supported
→ FFmpeg when required
```

### Stream Inspector handoff

Expected route:

```text
Stream Inspector arguments
→ shared AiDM argument parser
→ normalized streaming context
→ stream routing
→ yt-dlp with captured browser context
```

The Inspector-selected media candidate is authoritative.

AiDM must not rerank or silently substitute another browser candidate.

### Naked HLS/DASH URL

Naked stream URLs remain a supported feature.

Expected behavior:

```text
naked HLS/DASH URL
→ attempt normal stream handling
→ success: complete normally
→ failure caused by missing browser context: user may use Stream Inspector
```

The extension is assistance when browser context is required, not a mandatory step for every stream.

AiDM should not fabricate browser context for naked stream URLs.

### Direct HTTP/HTTPS file

Expected route:

```text
direct file
→ direct-file classifier
→ aria2c
```

### Generic supported website/media URL

Broad yt-dlp fallback belongs after more specific classifiers.

Expected route:

```text
generic supported URL
→ yt-dlp fallback
```

---

## Routing invariants

The following matrix is a permanent regression contract for the unified router.

| Input family | Expected classifier | Destination |
| --- | --- | --- |
| Single YouTube video | YouTube detector | yt-dlp → aria2c / FFmpeg as appropriate |
| YouTube playlist | Playlist detector | YouTube playlist workflow |
| Multiple YouTube videos | YouTube bulk detector | YouTube bulk workflow |
| Single direct URL | Direct detector | aria2c |
| Multiple direct URLs | Direct bulk detector | sequential/parallel aria2c |
| Local `.torrent` file | Torrent-path detector | aria2c |
| Naked HLS/DASH | Stream detector | yt-dlp native |
| Stream Inspector payload | Handoff parser + stream route | yt-dlp with captured context |
| Generic supported webpage | Generic fallback | yt-dlp |
| Unsupported or malformed input | Validation | useful error |

Once a capability is working in the integration branch, later merges and milestones are not allowed to break it.

---

## Important anti-patterns

The integration must avoid the following mistakes.

### Do not let streaming seize the whole gate

Wrong:

```text
parse Stream Inspector options
→ assume remaining input is always streaming
```

The Stream Inspector handoff is one recognized input form among several.

### Do not validate HTTP/HTTPS before torrent detection

Wrong:

```text
HTTP validation
→ torrent detection
```

A local torrent path would be rejected before reaching its proper classifier.

### Do not treat every multi-input invocation as direct bulk

Multiple URLs may be YouTube URLs.

The group must be classified before selecting a bulk workflow.

### Do not probe before cheap deterministic classification

Known patterns such as YouTube hostnames, playlist structure, torrent file paths, and obvious direct extensions should be handled before unnecessary network probing when practical.

### Do not resolve `aidm.py` conflicts with blind file replacement

During integration, `aidm.py` conflicts represent overlapping capabilities.

Conflict resolution must combine behaviors deliberately.

Do not simply choose:

```text
ours
```

or:

```text
theirs
```

for the whole router file if doing so would erase previously integrated intelligence.

Think in capabilities, not complete-file ownership.

---

## Stream Inspector legacy cleanup

Before branch integration, `feat/Streaming-URLs` should receive a small cleanup milestone.

The old Stream Detector syntax:

```text
URL|User-Agent=...&Referer=...
```

is considered obsolete for the future architecture.

It existed before AiDM Stream Inspector supplied a richer browser-observed handoff.

The old custom delimiter grammar should therefore be removed.

However, reusable infrastructure must remain.

### Remove

- legacy pipe-delimited Stream Detector parsing;
- obsolete assumptions that exist only to compensate for the lack of Stream Inspector data;
- generic legacy handoff glue that the new argument-based contract will replace.

### Preserve

- naked stream URL support;
- `StreamInput` as the internal streaming representation;
- request-header plumbing;
- stream-type detection;
- direct-file detection;
- YouTube detection;
- generic yt-dlp fallback;
- filename sanitization;
- subprocess execution using argument lists;
- architecture compatible with multiple positional inputs.

Milestone 0 cleanup must not implement the new Stream Inspector argument contract yet.

---

## Stream Inspector handoff direction

The browser extension currently exports a single-line, POSIX-shell-safe argument fragment.

The expected AiDM-side fields are:

```text
--user-agent
--referer
--subtitle    # repeatable
--title
MEDIA_URL
```

A future example:

```text
python aidm.py --user-agent 'Mozilla/5.0 ...' --referer 'https://player.example/' --subtitle 'https://cdn.example/sub.vtt' --title 'Example Movie' 'https://cdn.example/master.m3u8?token=...'
```

The parser must remain compatible with the broader AiDM CLI.

The whole application must not be redesigned around a permanently single streaming URL merely because a Stream Inspector handoff contains one selected media candidate.

The distinction is:

```text
AiDM parser
→ supports broad AiDM input

router
→ recognizes a Stream Inspector invocation

stream route
→ expects one selected media candidate
```

not:

```text
whole AiDM parser
→ permanently designed around one stream URL
```

---

## Milestone plan

### Milestone 0A — Streaming battlefield cleanup

Branch:

```text
feat/Streaming-URLs
```

Goal:

Remove obsolete Stream Detector handoff logic without implementing the new Inspector contract and without weakening future routing compatibility.

Success means:

- legacy pipe syntax is gone;
- naked streaming still works;
- reusable streaming structures remain;
- no new Inspector flags are introduced yet;
- nothing makes YouTube, direct, bulk, torrent, or generic routing harder to integrate later.

Only after this milestone passes should branch integration begin.

---

### Milestone 0B — Create the integration branch

Create from:

```text
main
```

Recommended branch:

```text
integration/aidm-unified-router
```

`main` remains untouched during the integration experiment.

---

### Milestone 0C — Merge feature branches one at a time

Merge feature branches into the integration branch one by one.

A practical sequence may be:

```text
feat/bulk-direct-downloads
→ feat/2ndry-features
→ feat/youtube
→ cleaned feat/Streaming-URLs
```

The exact order may be adjusted if Git history makes another order safer.

The invariant is more important than the order:

```text
merge one branch
→ resolve conflicts deliberately
→ test all capabilities accumulated so far
→ commit successful integration state
→ only then merge the next branch
```

Do not merge all branches at once and debug the combined result afterward.

---

### Milestone 0D — Unified routing baseline

After all feature branches are integrated, run the complete routing regression matrix.

The integration branch should successfully preserve:

- single YouTube;
- YouTube playlists;
- YouTube bulk;
- single direct downloads;
- direct bulk sequential;
- direct bulk parallel;
- torrent handling;
- naked HLS/DASH;
- generic yt-dlp fallback;
- useful invalid-input behavior.

Only after this baseline is green is branch unification considered complete.

This becomes the new development baseline for Stream Inspector work.

---

### Milestone 1 — Stream Inspector parser contract

Add support for:

```text
--user-agent
--referer
--subtitle
--title
MEDIA_URL
```

Requirements:

- `--subtitle` must be repeatable;
- optional fields must remain optional;
- shell-decoded values must be preserved exactly;
- the parser should be reusable by a future GUI;
- the broader multi-input AiDM architecture must remain intact;
- no router regression is acceptable.

---

### Milestone 2 — Normalize Inspector data

Convert parsed Inspector fields into AiDM's internal streaming representation.

Conceptually:

```text
Inspector CLI arguments
→ normalized StreamInput/context
→ URL
→ headers
→ title
→ subtitles
```

Downloader code should consume normalized values rather than repeatedly reading raw argparse fields.

---

### Milestone 3 — Main media handshake

Make a real Stream Inspector export successfully reach the existing HLS/DASH downloader path.

Requirements:

- selected URL remains unchanged;
- captured User-Agent reaches yt-dlp;
- captured Referer reaches yt-dlp;
- supplied title controls output basename after AiDM sanitization;
- Inspector title bypasses obsolete manual-title behavior;
- AiDM does not rerank browser candidates;
- naked stream URL support still works.

Success requires a genuine browser-captured stream to download end-to-end.

---

### Milestone 4 — No-subtitle workflow

A Stream Inspector handoff with no subtitle must remain a fully valid case.

Expected result:

```text
Movie.<media-extension>
```

No subtitle warning, discovery attempt, or fabricated subtitle should occur.

---

### Milestone 5 — Single subtitle sidecar

Add explicit download of one browser-observed subtitle URL.

Requirements:

- preserve the supplied subtitle URL;
- pass relevant request context;
- share the sanitized media basename;
- favor a sidecar file;
- do not re-encode media merely to attach subtitles;
- optional subtitle failure must not invalidate a successfully downloaded main media file.

---

### Milestone 6 — Multiple subtitle sidecars

Support repeated subtitle arguments.

Requirements:

- no silent overwrite;
- deterministic collision-safe naming;
- no invented language metadata when the extension does not provide it;
- zero, one, and multiple subtitle cases remain distinct and valid.

---

### Milestone 7 — Full unified regression gate

Run both new Stream Inspector cases and all previously integrated feature routes.

New-path checks should include:

- Inspector HLS/DASH with title;
- Inspector context with User-Agent and Referer;
- no subtitle;
- one subtitle;
- multiple subtitles;
- missing optional User-Agent;
- missing optional Referer;
- missing title where supported;
- apostrophes in titles;
- signed URLs containing shell-significant punctuation.

Existing-path checks must include all routing invariants from Milestone 0D.

A milestone fails if new streaming functionality succeeds while an existing feature route regresses.

---

## Deferred work

### GUI

The future AiDM GUI should reuse the same parser.

Conceptually:

```text
GUI paste box
→ shlex.split()
→ shared argparse parser
→ shared router
```

No separate GUI grammar should be created.

### Browser cookies/session strategy

Cookie/session integration remains deferred until a clear browser-extension contract exists.

AiDM must not infer browser identity from User-Agent text or invent a `--cookies-from-browser` source.

### Automatic direct extension-to-AiDM communication

The current manual clipboard handoff is sufficient for the beta architecture.

Direct IPC/native messaging can be considered later without changing the routing principles documented here.

---

## Development discipline

The project will follow a strict milestone gate.

```text
define one milestone
→ give Codex only that milestone
→ inspect the diff
→ test the milestone
→ run routing regression checks
→ success
→ commit
→ move to next milestone
```

Codex must not combine future milestones, redesign unrelated subsystems, or make speculative changes outside the requested scope.

A local feature result is not enough.

For this integration work:

> routing integrity is part of every milestone's definition of done.

---

## Final target

The intended user experience is:

```text
python aidm.py [INPUT]
```

The user supplies what they have.

AiDM decides what it is.

AiDM routes it to the correct engine and workflow.

If a naked stream works without browser context, it downloads normally.

If the stream requires browser context, AIDM Stream Inspector supplies that context and the same AiDM gate understands the handoff.

The user should not need to understand yt-dlp, aria2c, FFmpeg, HLS, DASH, browser headers, playlist routing, or internal engine selection merely to start a download.

That classification intelligence is part of AiDM itself.
