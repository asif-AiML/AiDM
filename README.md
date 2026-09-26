# AiDM

**AiDM** is a terminal-first download manager for Linux that automatically classifies what the user gives it and routes the job to the appropriate download workflow.

AiDM combines:

- **aria2c** for direct downloads and torrents;
- **yt-dlp** for website extraction, YouTube, HLS/DASH and generic media handling;
- **FFmpeg** where post-processing, merging or conversion is required;
- the companion **[AIDM Stream Inspector](https://github.com/asif-AiML/AIDM-Stream-Inspector-Browser-Extension-)** browser extension when a streaming session requires browser-observed request context.

The goal is simple:

```text
python aidm.py [whatever you have]
```

AiDM should decide what the input is and route it without asking the user to understand the internal downloader stack.

---

## Project status

AiDM has reached its **feature-complete beta architecture**.

The first beta release, `v0.1.0-beta`, is now published on `main` after the final real-world validation and regression suite passed successfully, including the Stream Inspector media + subtitle workflow.

Validated core capabilities include:

- single direct HTTP/HTTPS downloads;
- bulk direct downloads;
- sequential and parallel direct-bulk modes;
- local `.torrent` files;
- single YouTube videos;
- multiple YouTube videos;
- YouTube playlists;
- YouTube video/audio modes;
- naked HLS/DASH stream URLs;
- generic yt-dlp fallback;
- Stream Inspector argument handoff;
- captured User-Agent and Referer propagation;
- browser-derived title handoff and filename sanitization;
- optional subtitle sidecar workflow;
- unified routing that keeps these workflows separated instead of forcing every input through one downloader.

The normal maintenance model from this point is:

```text
main
  ↓
small fix/feature branch
  ↓
targeted test + regression
  ↓
merge back to main
```

---

## Why AiDM exists

Linux already has excellent download tools.

The problem is that the user often has to know **which one to use**, which flags belong to it, and what kind of input they actually have.

A direct file URL is not the same problem as:

- a YouTube video;
- a YouTube playlist;
- ten direct files;
- a torrent file;
- an HLS master playlist;
- a DASH manifest;
- a browser-observed signed stream;
- a generic website supported by yt-dlp.

AiDM exists to put a routing layer in front of those tools.

Conceptually:

```text
user input
    ↓
AiDM
    ↓
classify
    ↓
choose workflow
    ↓
aria2c / yt-dlp / FFmpeg
```

The routing intelligence is part of AiDM itself.

---

## Core philosophy

AiDM follows several rules throughout the project:

- classify before choosing a downloader;
- use narrow deterministic classifiers before broad fallbacks;
- keep working download engines instead of reimplementing them;
- preserve naked stream support even when Stream Inspector exists;
- do not fabricate browser context for ordinary URLs;
- preserve signed/tokenized URLs exactly;
- keep browser observation in the browser extension and downloading in AiDM;
- prefer subprocess argument lists over shell command construction;
- avoid speculative cookies, Origin handling or browser inference without evidence;
- protect already-working routes whenever a new feature is added;
- treat real-world failures as evidence to investigate, not automatic proof that the architecture is wrong.

---

## Unified routing

The current high-level router behaves conceptually like this:

```text
python aidm.py [INPUT]
        ↓
     AiDM gate
        ↓
 classify input
        │
        ├── local .torrent
        │      ↓
        │    aria2c
        │
        ├── multiple YouTube URLs
        │      ↓
        │    YouTube bulk
        │
        ├── multiple direct URLs
        │      ↓
        │    sequential / parallel aria2c
        │
        ├── YouTube playlist
        │      ↓
        │    yt-dlp workflow
        │
        ├── YouTube video
        │      ↓
        │    yt-dlp + aria2c where supported
        │
        ├── HLS / DASH
        │      ↓
        │    yt-dlp native
        │
        ├── direct HTTP file
        │      ↓
        │    aria2c
        │
        └── generic supported URL
               ↓
             yt-dlp
```

The user does not manually select the underlying engine.

---

## Companion project: AIDM Stream Inspector

Some streaming URLs work when copied directly.

Others do not.

A browser session may depend on:

- a signed or short-lived URL;
- User-Agent;
- Referer;
- page/session context;
- the correct parent/master media candidate rather than a child rendition;
- subtitle resources discovered separately from the main media.

That problem belongs partly inside the browser.

For those cases AiDM has a companion project:

**[AIDM Stream Inspector](https://github.com/asif-AiML/AIDM-Stream-Inspector-Browser-Extension-)**

The extension is the browser-intelligence layer.

AiDM is the downloader/router layer.

### Responsibility boundary

```text
AIDM Stream Inspector
→ observe browser playback traffic
→ detect media
→ rank candidates
→ discover subtitles
→ discover title
→ preserve useful request context
→ let the user select
→ export a handoff

AiDM
→ parse the handoff
→ classify
→ reproduce useful request context
→ download media
→ download supported subtitle sidecars
→ merge/post-process when required
→ name output files
```

Neither project needs to become the other.

---

## The browser-to-AiDM handshake

The current beta bridge is intentionally manual and inspectable.

The extension produces a POSIX-shell-safe argument fragment such as:

```text
--user-agent 'Mozilla/5.0 ...' --referer 'https://player.example/' --subtitle 'https://cdn.example/sub.vtt' --title 'Example Movie' 'https://cdn.example/master.m3u8?token=...'
```

The user runs:

```bash
python aidm.py [PASTE]
```

AiDM accepts these Stream Inspector fields:

```text
--user-agent
--referer
--subtitle
--title
MEDIA_URL
```

A valid Stream Inspector handoff represents one selected authoritative media candidate.

AiDM does not rerank or silently replace that selected browser candidate.

---

## First successful real Stream Inspector handshake

The first full real-world browser-assisted handshake was achieved on **2026-09-25**.

The test was especially meaningful because the same streaming session produced both a baseline and an assisted case:

```text
Naked HLS URL
→ failed

Same session + Stream Inspector context
→ HLS recognized
→ 1371 fragments discovered
→ title-based destination created
→ download started
```

The successful run reached:

```text
Input type: HLS stream
Extractor/downloader: yt-dlp native
Post-processing: FFmpeg when required
```

and yt-dlp reported:

```text
[hlsnative] Total fragments: 1371
```

before beginning the media download.

That test demonstrated the architecture the project had been building toward:

```text
Browser
→ Stream Inspector
→ AiDM
→ yt-dlp
→ media fragments
```

The detailed milestone record is preserved in:

```text
docs/milestone-3-stream-inspector-handshake-success.md
```

---

## Direct downloads

A single obvious direct HTTP/HTTPS file is routed to aria2c.

Example:

```bash
python aidm.py 'https://example.com/file.iso'
```

AiDM prints the selected input type and engine before handing the job to aria2c.

---

## Bulk direct downloads

Multiple direct URLs are classified as one direct batch.

Example:

```bash
python aidm.py 'https://example.com/a.zip' 'https://example.com/b.zip'
```

AiDM presents:

```text
Choose Mode: [1/2]

1 - Sequential
2 - Parallel
```

### Sequential

Downloads one file at a time and shows item progress such as:

```text
[1/2] Downloading...
```

### Parallel

Hands the batch to aria2c for concurrent downloading.

---

## Torrent files

Local `.torrent` files are routed directly to aria2c.

Example:

```bash
python aidm.py './example.torrent'
```

Torrent detection intentionally happens before HTTP/HTTPS validation so a local path is not incorrectly rejected as a malformed URL.

---

## YouTube

AiDM has a dedicated YouTube workflow rather than treating YouTube as an ordinary generic URL.

Supported areas include:

- single videos;
- multiple video URLs;
- playlists;
- video mode;
- original best-quality audio;
- WAV audio conversion;
- playlist quality discovery/selection.

Example:

```bash
python aidm.py 'https://www.youtube.com/watch?v=...'
```

AiDM then presents the applicable YouTube mode menu.

### Multiple YouTube videos

Multiple YouTube URLs are recognized as a YouTube batch rather than being mistaken for direct-file bulk input.

### Playlists

Playlist URLs are recognized before ordinary YouTube video routing.

The playlist workflow can inspect available heights and let the user choose a target quality before downloading.

---

## Streaming: naked HLS/DASH

Stream Inspector is **not mandatory** for every stream.

A naked HLS or DASH URL remains a first-class AiDM input.

Example:

```bash
python aidm.py 'https://cdn.example/master.m3u8'
```

AiDM probes the resource and can classify:

- HLS;
- DASH;
- WebVTT.

When an HLS/DASH stream works without additional browser context, AiDM downloads it normally.

If the same stream requires browser-derived context, Stream Inspector can provide it.

The intended rule is:

```text
naked stream works
→ use it directly

naked stream fails because browser context matters
→ use Stream Inspector
```

---

## Browser request context

For a Stream Inspector invocation, AiDM can normalize captured request context into its internal `StreamInput`.

Currently supported handoff headers are:

- User-Agent;
- Referer.

These values can be used both during stream detection and during the media request.

AiDM does not fabricate missing Inspector headers.

### Cookies

Cookies are not part of the current beta handoff contract.

AiDM does not currently:

- infer the browser from User-Agent;
- invent a browser profile;
- automatically add `--cookies-from-browser`;
- accept raw cookie handoff as part of the normal Stream Inspector workflow.

This remains deliberately deferred until reproducible evidence justifies a concrete design.

### Origin

Origin is also excluded from the current handoff contract.

It can be reconsidered later if real provider testing proves that it is required.

---

## Titles and output naming

Stream Inspector may supply a canonical playback title.

AiDM owns filesystem naming.

The title is therefore passed through AiDM's filename sanitization before being used as an output basename.

Conceptually:

```text
browser playback title
→ Stream Inspector
→ --title
→ StreamInput.title
→ sanitize_filename()
→ yt-dlp output template
```

No old interactive movie-title prompt is required.

Naked streams without an Inspector title retain natural downloader naming.

---

## Subtitle sidecars

Stream Inspector can hand AiDM a browser-observed subtitle URL.

The beta workflow treats subtitles as sidecar files rather than re-encoding the media merely to embed them.

The intended result is:

```text
Movie Title.mp4
Movie Title.vtt
```

or the corresponding detected subtitle extension.

The subtitle uses the same sanitized title basename as the main media and sits beside it in the current output directory.

The main media remains primary:

```text
media fails
→ overall download fails

media succeeds + subtitle succeeds
→ full success

media succeeds + optional subtitle fails
→ media remains successful
→ subtitle warning
```

A handoff with no subtitle is completely valid.

Broader multi-subtitle naming/selection behavior can continue to evolve after the initial beta.

---

## Generic yt-dlp fallback

Not every useful URL has a cheap deterministic classifier.

After more specific AiDM routes have had a chance to match, a generic supported website/media URL can fall through to yt-dlp.

This fallback deliberately belongs late in routing precedence so it does not steal:

- torrents;
- YouTube-specific behavior;
- direct files;
- recognized HLS/DASH streams.

---

## Download engines

AiDM orchestrates proven external tools rather than replacing them.

### aria2c

Used for areas such as:

- direct HTTP/HTTPS files;
- direct bulk downloads;
- torrent files;
- yt-dlp delegation where supported;
- concrete subtitle sidecar resources where applicable.

### yt-dlp

Used for areas such as:

- YouTube;
- HLS/DASH;
- supported websites/media extraction;
- generic fallback.

### FFmpeg

Used by workflows where conversion, merging or post-processing is required, including WAV conversion and media operations requested by yt-dlp.

---

## Requirements

AiDM currently expects these tools to be available on the system `PATH`:

```text
Python 3
yt-dlp
aria2c
FFmpeg
```

On Debian/Ubuntu/Linux Mint systems, aria2 and FFmpeg are commonly available through APT:

```bash
sudo apt update
sudo apt install aria2 ffmpeg
```

Install yt-dlp using a current supported installation method for your distribution/environment, then verify the tools are visible:

```bash
python3 --version
yt-dlp --version
aria2c --version
ffmpeg -version
```

Additional project installation notes are kept under:

```text
Requirements/
```

---

## Basic usage

From the repository root:

```bash
python aidm.py [INPUT]
```

Examples:

### Direct file

```bash
python aidm.py 'https://example.com/file.zip'
```

### Multiple direct files

```bash
python aidm.py 'https://example.com/a.zip' 'https://example.com/b.zip'
```

### Torrent

```bash
python aidm.py './example.torrent'
```

### YouTube

```bash
python aidm.py 'https://www.youtube.com/watch?v=...'
```

### Naked stream

```bash
python aidm.py 'https://cdn.example/master.m3u8'
```

### Stream Inspector

Copy the argument fragment from AIDM Stream Inspector and paste it after:

```bash
python aidm.py [PASTE]
```

---

## Output location

AiDM currently operates CLI-first and writes downloader output relative to the current working directory unless the underlying workflow specifies otherwise.

This keeps the command-line behavior predictable:

```text
cd where/you/want/the/files
python aidm.py ...
```

---

## Architecture overview

A simplified view:

```text
                       AiDM CLI
                          ↓
                    shared argparse
                          ↓
                    unified router
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
     YouTube            Direct           Torrent
        │                 │                 │
     yt-dlp             aria2c            aria2c
        │
 aria2c / FFmpeg
 where appropriate

                          │
                          ↓
                       Streaming
                          │
              ┌───────────┴───────────┐
              │                       │
          naked URL          Stream Inspector
              │                       │
              └───────────┬───────────┘
                          ↓
                     StreamInput
                          ↓
                  HLS/DASH detection
                          ↓
                       yt-dlp
```

---

## Internal streaming model

Browser-assisted streaming data is normalized into one internal representation instead of letting downloader functions read CLI flags directly everywhere.

Conceptually:

```text
argparse.Namespace
        ↓
StreamInput
 ├─ url
 ├─ headers
 ├─ stream_type
 ├─ title
 └─ subtitles
        ↓
downloader
```

This separation is intentional.

It keeps downloader behavior independent from the exact CLI syntax and leaves room for a future GUI to reuse the same parser/router.

---

## Future GUI compatibility

The current Stream Inspector clipboard format is designed so a future AiDM GUI can reuse it.

Conceptually:

```text
Stream Inspector
        ↓
one-line shell-safe argument fragment
        ↓
┌──────────────────────────┐
│ Terminal                 │
│ OS shell → argv          │
├──────────────────────────┤
│ Future GUI               │
│ shlex.split(text) → argv │
└──────────────────────────┘
        ↓
shared AiDM parser
        ↓
shared router
```

The future GUI should not create a second handoff grammar and should not execute pasted text with `shell=True`.

GUI work is outside the current beta scope.

---

## Repository structure

The current core is intentionally small:

```text
.
├── aidm.py
├── detector.py
├── downloader.py
├── stream_parser.py
├── utils.py
├── youtube.py
├── Requirements/
└── docs/
```

### `aidm.py`

Main CLI entry point and unified routing gate.

### `detector.py`

Input classification helpers including YouTube, playlist, direct-file and torrent-related detection.

### `downloader.py`

aria2c / yt-dlp / stream download command construction and execution paths.

### `stream_parser.py`

Internal `StreamInput` model and HLS/DASH/VTT stream probing.

### `youtube.py`

YouTube-specific modes, quality handling, playlist workflow and multi-URL behavior.

### `utils.py`

Shared helpers such as command execution and filename sanitization.

### `docs/`

Architecture decisions, integration history, Stream Inspector handoff contract and milestone records.

---

## Routing regression contract

AiDM's unified router has been repeatedly tested against its major route families.

The permanent regression set includes:

```text
1. single direct URL
2. direct bulk sequential
3. direct bulk parallel
4. local .torrent
5. single YouTube video
6. multiple YouTube videos
7. YouTube playlist
8. naked HLS/DASH
9. generic yt-dlp / mixed-bulk behavior
```

The Stream Inspector real-world workflow adds the browser-assisted streaming test on top of that baseline.

A new feature is not considered successful if it works locally while breaking one of the established routes.

---

## Development history

AiDM evolved through separate feature branches before the current unified router was established.

Important development areas included:

```text
direct downloads
→ YouTube
→ naked HLS/DASH
→ bulk direct
→ torrent
→ YouTube bulk/playlist quality work
→ Stream Inspector browser intelligence
→ unified integration router
→ Inspector parser contract
→ normalized streaming context
→ real browser-assisted main-media handshake
→ subtitle sidecar workflow
```

The separate feature branches were intentionally preserved during integration as known-good references.

A detailed integration record is available in:

```text
docs/unified-integration-routing-plan.md
```

---

## Testing philosophy

AiDM is developed with small milestones and explicit regression gates:

```text
small feature
→ inspect
→ test
→ verify existing routes
→ commit
→ next feature
```

Streaming providers are volatile.

Tokens expire, CDNs change, anti-bot behavior changes, and one provider may behave differently from another.

Therefore:

> One failed real-world URL is evidence for investigation, not automatic proof that the entire architecture is wrong.

Controlled comparisons are preferred.

The first successful Stream Inspector handshake itself used this approach: a naked URL failed, then the same session succeeded once browser-observed request context was supplied.

---

## What AiDM does not do

The current beta does not aim to:

- bypass DRM;
- defeat access-control systems;
- guarantee that every signed URL remains valid;
- automatically export browser cookies;
- infer browser profiles;
- automatically communicate with the extension through native messaging;
- provide a GUI;
- replace yt-dlp, aria2c or FFmpeg;
- hide every warning emitted by upstream tools;
- guarantee every website supported today will remain unchanged tomorrow.

AiDM coordinates tools and reproduces supported browser-observed context; it does not remove server-side restrictions.

---

## DRM and access-control boundary

AiDM and AIDM Stream Inspector are intended for ordinary downloadable/browser-visible media workflows.

They are not designed to defeat DRM or other access-control systems.

External reproduction can still fail because of:

- expired signatures;
- network/IP restrictions;
- account state;
- anti-bot systems;
- DRM/license exchange;
- provider-side policy.

Visible browser traffic does not automatically imply that an external downloader can reproduce it.

---

## Security notes

Signed media URLs and browser-derived request context may contain sensitive temporary values.

Project practice therefore avoids:

- committing real captured signed URLs/tokens;
- embedding live credentials in source code;
- constructing commands through `shell=True`;
- treating exported Stream Inspector fragments as permanent credentials.

Externally supplied values are kept as separate subprocess argument-list elements inside AiDM.

Users should treat copied signed media URLs as potentially sensitive while they remain valid.

---

## Relationship with AIDM Stream Inspector

[AIDM Stream Inspector](https://github.com/asif-AiML/AIDM-Stream-Inspector-Browser-Extension-) is the official companion browser project for AiDM.

The two projects were developed in parallel around the same boundary:

```text
Browser understands the playback session.
AiDM performs the download.
```

The current bridge is:

```text
Browser playback
    ↓
AIDM Stream Inspector
    ↓
Copy for AiDM
    ↓
clipboard argument fragment
    ↓
AiDM CLI
    ↓
yt-dlp / aria2c / FFmpeg
```

The repositories remain separate because their responsibilities are separate.

---

## Beta scope

The initial beta intentionally focuses on a strong CLI and an explicit manual browser handoff.

Not required for the first beta:

- GUI;
- native messaging;
- automatic extension-to-AiDM IPC;
- provider-specific automation;
- speculative cookie/profile integration;
- broad multi-subtitle intelligence;
- terminal cosmetic cleanup.

Those can be added later when real usage provides evidence that they are worth the complexity.

---

## Version

Current beta release:

```text
v0.1.0-beta
```

AiDM and AIDM Stream Inspector intentionally use aligned early versioning because they were developed as companion halves of the same browser-assisted download architecture.

The `v0.1.0-beta` tag marks the first completed beta baseline on `main`.

---

## Documentation

The `docs/` directory preserves deeper project history and design decisions, including:

- unified integration and routing;
- Stream Inspector handoff architecture;
- browser-context decisions;
- streaming experiments;
- real handshake milestones;
- regression expectations.

The README describes what AiDM is now.

The detailed documents preserve how and why it became that system.

---

## Summary

AiDM turns heterogeneous download inputs into one Linux-first workflow.

It:

```text
accepts
→ classifies
→ routes
→ downloads
→ merges/converts when required
→ names output
→ optionally works with browser-observed streaming context
```

And when the browser knows something the naked URL does not, its companion Stream Inspector supplies that missing context.

> **AIDM Stream Inspector understands the browser playback session; AiDM turns that understanding into a download.**
