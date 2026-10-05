# AiDM GUI Master Plan

## Purpose

This document is the master reference for the first AiDM graphical user interface.

It records the GUI behavior, UX rules, architectural boundaries, backend/frontend responsibilities, and feature scope that were agreed before implementation begins.

The GUI is not intended to replace the mature CLI or become a separate implementation of AiDM. It is a second frontend over the same download intelligence.

The core principle is:

```text
CLI functionality = GUI functionality
```

The first GUI must expose the capabilities already proven in the CLI without silently inventing new backend features.

---

## Development branch strategy

GUI development begins from the mature `main` branch.

Development branch:

```text
feat/gui
```

The intended branch relationship is:

```text
main
├─ mature CLI
├─ tested router
├─ tested downloader behavior
└─ v0.1.0-beta baseline

        ↓ branch from main

feat/gui
├─ GUI frontend
├─ GUI state management
├─ DownloadJob model
├─ progress/event plumbing
└─ shared-core refactoring where required
```

The GUI branch is a construction zone, not a permanent second product line.

Once the GUI reaches a stable, tested milestone, it should merge back into `main`.

Long-term target:

```text
main
├─ CLI frontend
├─ GUI frontend
├─ shared AiDM core
└─ one source of truth
```

Future backend features should continue to follow this sequence:

```text
backend feature
→ CLI implementation
→ CLI validation
→ regression testing
→ GUI exposure
```

This prevents the GUI and CLI from developing separate intelligence.

---

# 1. Product philosophy

AiDM should remain visually modest while retaining strong intelligence underneath.

The GUI should feel:

- minimal;
- flexible;
- progressively revealed;
- context-aware;
- truthful;
- fast to understand;
- free of unnecessary controls;
- consistent with AiDM's terminal-first architecture.

The GUI should not resemble a large traditional download-manager dashboard full of permanent controls.

Instead:

```text
paste input
→ AiDM understands the job
→ show only the controls needed for that job
```

Options belong to the current download job, not permanently to the application.

---

# 2. The GUI is a frontend, not a new downloader

The GUI must not reimplement the routing logic.

The desired architecture is:

```text
                AiDM Core
                   │
          ┌────────┴────────┐
          │                 │
        CLI GUI
          │                 │
          └──── same core ──┘
                   ↓
         aria2c / yt-dlp / FFmpeg
```

The core remains responsible for:

- input classification;
- routing;
- downloader selection;
- stream context handling;
- YouTube workflows;
- direct workflows;
- HLS/DASH workflows;
- naming;
- subtitle handling;
- post-processing;
- backend status;
- download telemetry.

The GUI is responsible for:

- displaying state;
- collecting user choices;
- rendering progress;
- choosing destination folders;
- showing contextual controls;
- translating backend events into a clean visual experience.

The GUI must not reconstruct shell commands and should not depend on `shell=True`.

---

# 3. Flexible minimal visual design

The foundational design is a modest application window that begins extremely simple and expands only when necessary.

At rest, the UI should contain only the essentials:

```text
┌────────────────────────────────┐
│ AiDM                           │
│                                │
│ [ Paste URL or AiDM data     ] │
└────────────────────────────────┘
```

No empty progress bar.

No fake zero-speed readout.

No unused title area.

No disabled controls that do not yet matter.

The window becomes richer only after meaningful input is provided.

This progressive reveal behavior is a central design rule.

---

# 4. Window shape and visual treatment

The visual direction favors:

- a modest rectangular application window;
- rounded content elements;
- a clean input field;
- a colorized progress bar;
- rounded buttons;
- restrained use of spacing;
- minimal visual noise.

For the first GUI version, native Linux window chrome should be preferred instead of immediately implementing a fully custom frameless window.

Reason:

a custom outer window frame would force AiDM to own:

- dragging;
- resizing;
- minimize behavior;
- close behavior;
- shadows;
- maximize behavior;
- window-manager differences.

The first implementation should spend complexity on useful behavior, not on recreating desktop window management.

Rounded content inside the application is fully compatible with the intended design.

---

# 5. Primary UI states

The GUI should behave as an explicit state machine.

Core states:

```text
EMPTY
  ↓
INSPECTING
  ↓
READY          ← passive inspection complete; Download/Enter accepts intent
  ↓
NEEDS OPTIONS  ← only after Download/Enter, and only when choices are required
  ↓
READY          ← configured DownloadJob; next Download/Enter is execution intent
  ↓
DOWNLOADING    ← Milestone 10: DIRECT_SINGLE only; other routes deferred
  ↓
COMPLETE
```

Failure may occur from relevant states:

```text
FAILED
```

Not every input must visit every state.

A simple direct URL may go:

```text
EMPTY
→ INSPECTING
→ READY
→ DOWNLOADING
→ COMPLETE
```

A YouTube video may go:

```text
EMPTY
→ INSPECTING
→ READY (passive)
→ Download/Enter
→ NEEDS OPTIONS
→ READY (configured)
→ Download/Enter
→ DOWNLOADING
→ COMPLETE
```

This state model should guide both frontend behavior and backend event design.

---

# 6. Input field behavior

The main input field accepts:

- ordinary URLs;
- multiple URLs where supported;
- YouTube URLs;
- direct-download URLs;
- naked HLS/DASH URLs;
- generic supported URLs;
- AIDM Stream Inspector handoff text.

A Stream Inspector handoff may look conceptually like:

```text
--user-agent '...' --referer '...' --subtitle '...' --title 'Movie' 'https://...m3u8'
```

The GUI should reuse the existing AiDM parser behavior.

For pasted Stream Inspector data:

```text
paste text
→ shlex.split()
→ existing AiDM parser
→ existing router
```

The GUI must not define a second handoff grammar.

---

# 7. Input recognition before download

The preferred UX is a hybrid of immediate classification and asynchronous metadata inspection.

## Immediate classification

When the input can be cheaply recognized without network work, AiDM should identify it as soon as possible.

Examples:

```text
YouTube URL
→ YouTube video

Playlist URL
→ YouTube playlist

Multiple direct URLs
→ Direct batch

Stream Inspector arguments
→ Browser-assisted stream
```

This classification should appear before the user starts the download when possible.

## Background metadata inspection

Richer metadata may be fetched asynchronously.

Examples:

- YouTube title;
- playlist title;
- playlist item count where practical;
- HLS/DASH type;
- browser-provided media title.

For a single direct download, AiDM intentionally does **not** derive or fetch a
pre-download filename/title. The filename/name slot remains empty until the
actual download begins and aria2c reveals the resolved output filename.

The interface may temporarily show:

```text
● YouTube video
  Fetching media information…
```

and later update to:

```text
● YouTube video
  Billionera – Otilia
```

Metadata fetching must not freeze the UI.

The Download button should not be blocked unnecessarily by slow metadata lookup.

---

# 8. Classification and title are separate information

The interface should distinguish:

1. what kind of job AiDM detected;
2. what media/file is being handled.

Example:

```text
● YouTube video
  Billionera – Otilia
```

or, before a direct download starts:

```text
● Direct download
```

Once aria2c starts the job, the resolved filename may appear in the same
title/name slot as runtime backend truth.

or:

```text
● HLS stream
  Spider-Man: Brand New Day
```

or:

```text
● YouTube playlist
  167 items
```

The classification line and media-title line should remain visually distinct.

---

# 9. Media title placement

The preferred reading order is:

```text
input
↓
classification
↓
media title
↓
progress
↓
download statistics
↓
status
↓
action button
```

This ordering is preferred over placing the title below the progress bar.

It answers:

```text
What am I downloading?
↓
How far has it gone?
↓
How fast / how much / how long?
```

---

# 10. Download button behavior

The Download button should appear only after AiDM has meaningful input.

At rest, there should be no unnecessary Download button.

Once passive classification identifies usable input, enter READY and show:

```text
[ Download ]
```

The Enter key should trigger Download when the job is in a READY state.

READY means the primary action is available, not necessarily that secondary
choices have been completed. First Download/Enter opens required configuration.
When choices form a valid DownloadJob, return to READY. A further Download/Enter
is execution intent. Simple routes skip configuration. Milestone 10 executes
DIRECT_SINGLE only. Other routes retain the validated job and show
"Download configured — execution is not implemented yet."

If metadata is still loading but the job is otherwise valid, pressing Enter should not be unnecessarily blocked.

---

# 11. Secondary user interaction must remain inline

Several existing CLI workflows require additional user choices.

The GUI should preserve those choices without popup-heavy interaction.

Routine choices appear inline only after explicit Download/Enter intent.
Passive paste/classification never reveals modes or starts quality discovery.
Order: input, classification, title, item count, secondary options, status,
Download (when READY). No mode or quality is implicitly preselected.

Video quality discovery uses the existing backend helper in a cancellable Qt
process with a 20-second timeout. It starts only on choosing Video, or on the
first Download/Enter for a playlist. During lookup show exactly:
"Fetching available video qualities…". Then show Quality [ Choose quality ▼ ].
Failure uses explicit VideoQuality.BEST and the calm status:
"Available qualities could not be determined — best available will be used."

Input changes clear all choices, qualities and jobs. Switching Video to audio,
resetting configuration or closing cancels discovery and invalidates its
generation; stale results cannot update the current input. Metadata/title
completion preserves the active configuration phase. F1–F7 remain test previews.

The principle is:

> The main window stays structurally familiar; job-specific options appear only when required.

Avoid using modal dialogs for routine download configuration.

---

# 12. CLI functionality equals GUI functionality

The first GUI must mirror the current mature CLI feature set.

Do not add new backend features merely because the GUI could display them.

Locked rule:

```text
CLI functionality = GUI functionality
```

If a future feature is desired, it should first be implemented and tested in the backend/CLI, then exposed in the GUI.

---

# 13. YouTube single-video behavior

Current CLI support for a single YouTube video includes:

- Video;
- Original Audio;
- WAV.

The first GUI should expose exactly these choices.

Example:

```text
● YouTube video
  Billionera – Otilia

Download as
[ Video ] [ Original Audio ] [ WAV ]

Save to
~/Downloads              [ Browse ]

                    [ Download ]
```

Milestone 7.2 adds backend/CLI video-quality selection after choosing Video,
reusing playlist discovery and the maximum-height format selector. Discovery
failure retains the existing best-available fallback. Audio/WAV are unchanged.
The backend has passed real CLI testing. Milestone 7.3 represents this choice
as `DownloadJob.video_quality`; Milestone 8 exposes it after explicit intent.

Milestone 8: first Download/Enter reveals Download as
[ Video ] [ Original Audio ] [ WAV ]. Choosing Video starts quality discovery;
only after it completes show Quality [ Choose quality ▼ ]. Hide the quality
control for Original Audio and WAV; these modes require no quality lookup.

---

# 14. YouTube bulk behavior

Current CLI support for YouTube bulk includes:

- Video;
- Original Audio;
- WAV.

The first GUI should expose those same choices.

Example:

```text
● YouTube batch
  10 videos

Download as
[ Video ] [ Original Audio ] [ WAV ]

Save to
~/Downloads              [ Browse ]

                    [ Download ]
```

Milestone 7.2 adds backend/CLI Video quality selection using only the first
normalized video URL as the representative source. One selected maximum height
applies to all videos, allowing lower available heights.

Milestone 8 uses the same intent-first controls as single video, with Quality
visible only for Video after lookup. One maximum-height choice applies to the batch.

---

# 15. YouTube playlist behavior

Current playlist behavior includes a quality selector.

Playlist audio modes are not part of the current backend and are not required for the first GUI.

Milestone 8: first Download/Enter starts quality discovery and then shows only
the quality selector, without a Video / Original Audio / WAV mode selector.

Example:

```text
● YouTube playlist
  167 items

Quality
[ 1080p ▼ ]

Save to
~/Downloads              [ Browse ]

                    [ Download ]
```

The GUI should expose only the playlist options already supported by the CLI.

---

# 16. Direct bulk behavior

Direct bulk requires a second user decision currently handled in the terminal:

- Sequential;
- Parallel.

The GUI should present this inline.

Example:

```text
● Direct batch
  10 files

Download mode

[ Sequential ]   [ Parallel ]

Save to
~/Downloads              [ Browse ]

                    [ Download ]
```

The exact default can be decided later based on real behavior and UX testing.

---

# 17. Destination folder selection

Once passive inspection produces usable input, the GUI shows the destination
folder alongside Download. It stays visible in NEEDS_OPTIONS during mode/quality
configuration. EMPTY, invalid and unsupported input keep this section hidden.

Preferred behavior:

```text
Save to
~/Downloads                         [ Browse ]
```

The user can click Browse to open the native folder picker.

The application should not force a folder-selection dialog for every download.

Milestone 9 behavior:

- Default to an existing accessible `Path.home() / "Downloads"`; otherwise use home.
  Do not create Downloads or use the repository working directory as the default.
- Display the full resolved path in a read-only, horizontally scrollable field
  with a full-path tooltip and a native Browse directory picker.
- Start Browse at the current folder. Cancelling leaves it unchanged.
- Remember valid Browse selections with `QSettings("AiDM", "AiDM")`, key
  `downloads/destination`. On startup, missing, non-directory or inaccessible
  saved paths fall back to Downloads/home.
- Preserve destination across input changes; reset only job-specific choices.
- Changing the folder rebuilds a completed DownloadJob without changing mode,
  quality or bulk selections. Pending quality discovery continues unchanged.
- The GUI validates directory existence and read/traverse access. This does not
  promise future write success; execution must handle write failures later.

Destination is general job context, not an intent-driven secondary choice.
Enter retains the primary Download behavior and does not open Browse.
Milestone 10 maps the direct-single job destination to aria2c `--dir`, after
revalidating the directory immediately before execution. An unavailable folder
is reported without silently redirecting the download. Tests inject temporary
INI settings and do not access the user's real preferences.

## Milestone 10 execution boundary

- Only `DownloadJob.kind == DIRECT_SINGLE` executes from the GUI. All other
  kinds, including Stream Inspector jobs with an underlying direct route, remain
  deferred.
- `downloader.build_direct_command(url, destination=None)` owns the existing
  aria2c arguments. The CLI wrapper still uses blocking `run_command`; omitting
  destination preserves its historical current-directory output behavior.
- `gui_execution.DirectDownloadProcess` launches that same command through
  asynchronous QProcess, with the job's absolute destination passed as `--dir`.
  It never changes the application working directory.
- READY transitions directly to DOWNLOADING, initially showing `Starting aria2c…`.
  The actual process-start signal changes the status to `Downloading…`.
  Input editing and Browse are disabled; configuration controls are hidden.
- A normal process exit with code zero shows `Download complete`; nonzero or
  crashed exits show `Download failed`. Failure to launch shows
  `Could not start aria2c.`. File existence alone does not imply success.
- Output is drained without progress parsing; only a bounded stderr tail is
  retained internally. No filename guessing, progress bar, telemetry or user-facing
  Abort is added. Explicit Abort remains deferred to Milestone 14.
- Closing terminates the child, waits up to one second, then kills and waits up
  to one more second if necessary. If the child has still not stopped, the window
  remains open to retain ownership. This is close-time hygiene only.

## Milestone 11 status-event channel

Execution activity follows `backend execution → StatusEvent → frontend renderer`.
The frozen, Qt-independent model in `status_event.py` contains only `kind`,
optional `engine`, and optional semantic `reason`. It carries neither UI sentences
nor raw stderr. The current kinds are STARTING_ENGINE, DOWNLOADING, COMPLETE and
FAILED; START_FAILED distinguishes failure to launch an engine.

For DIRECT_SINGLE, `DirectDownloadProcess.status_event` emits STARTING_ENGINE
for aria2c immediately before launch, DOWNLOADING on the actual QProcess started
signal, then COMPLETE on a normal zero exit or FAILED on nonzero/crashed exit.
Launch failure emits FAILED with START_FAILED, without a DOWNLOADING event.
Terminal status precedes the separate `finished(success)` signal. Closing keeps
the existing cleanup behavior and suppresses terminal UI notifications.

The GUI renderer translates the latest event into text. `GuiState` remains the
structural state authority: status events do not transition it, and terminal
state transitions depend only on `finished(success)`, never rendered text.
While active, only `active_status` shows activity; after completion/failure,
only `result_message` shows the result. Bounded stderr stays separate.

StatusEvent answers **what is happening**. Future ProgressEvent, beginning in
Milestone 12, answers **how far it has progressed**. No progress fields, parsing,
filename discovery or artificial finalization stage are introduced here.
Inspection/configuration statuses and the CLI renderer remain unchanged.

---

# 18. Torrent UI scope

Torrent support already exists in the CLI.

Torrent input is intentionally excluded from the first URL-focused GUI flow.

Later, torrent support should be exposed naturally through a file-browse interaction.

Conceptually:

```text
[ Paste URL or AiDM data ]

            or

       [ Browse File ]
```

The file picker can then support `.torrent`.

This keeps the first GUI focused and avoids forcing local file paths into a URL-centric input design.

---

# 19. Active download layout

When the real download begins, the UI should expand and reveal live information.

Example:

```text
● YouTube video
  Billionera – Otilia

██████████████──────────── 56%

5.3 MB/s • 312 MB / 558 MB • ETA 00:47

Downloading…

                          [ Abort ]
```

Core live information:

- progress percentage;
- download speed;
- ETA;
- total size when known;
- downloaded size;
- active title;
- status language;
- Abort action.

---

# 20. Progress must represent backend truth

The GUI must not invent progress.

The progress bar should reflect real data from the download engines.

Desired data flow:

```text
aria2c / yt-dlp
       ↓
structured progress event
       ↓
AiDM backend
       ↓
GUI
```

The GUI renders truth received from the backend.

It should never simulate progress based on elapsed time.

---

# 21. Structured telemetry instead of scraping terminal presentation

The GUI should not depend on parsing human-oriented terminal formatting if a more structured mechanism can be created.

Avoid making the GUI fragile against output changes such as:

```text
[download] 43.7% of 1.2GiB at 4.3MiB/s ETA 02:13
```

Preferred internal concept:

```text
ProgressEvent
├─ percent
├─ downloaded_bytes
├─ total_bytes
├─ speed
├─ eta
├─ title
└─ optional queue information
```

Conceptually:

```python
ProgressEvent(
    percent=43.7,
    downloaded_bytes=...,
    total_bytes=...,
    speed=...,
    eta=...,
    title=...,
)
```

The CLI renderer and GUI renderer can both consume backend truth without making the GUI depend on terminal cosmetics.

---

# 22. Core download statistics

The GUI should surface the four main statistics already provided by the engines where available:

1. Download speed
2. ETA
3. Full size
4. Downloaded size

A compact presentation is preferred.

Example:

```text
4.8 MB/s • 812 MB / 2.1 GB • ETA 04:37
```

Percentage can remain attached to the progress bar.

---

# 23. Missing telemetry must be handled gracefully

Not every protocol/provider exposes every metric.

For example, an HLS job may have reliable fragment progress but no trustworthy final byte size.

Every telemetry field should be treated as potentially optional.

The GUI must never fabricate unknown information.

Acceptable states include:

```text
782 MB downloaded
```

or:

```text
Total size: unknown
```

The UI should continue functioning even when:

- total size is unknown;
- ETA is unavailable;
- percentage is unavailable;
- speed is temporarily unknown.

---

# 24. Status language

A small human-readable status area is a required UX improvement.

Its purpose is to prevent the user from thinking AiDM has frozen during non-download phases.

Possible status values include:

Before download:

```text
Inspecting input…
Fetching media information…
Checking available qualities…
Ready
```

During download:

```text
Starting aria2c…
Starting yt-dlp…
Downloading…
Downloading item 4 of 10…
Downloading video…
Downloading audio…
Merging audio and video…
Downloading subtitle…
Finalizing…
```

Completion:

```text
Download complete
```

Failure:

```text
Download failed
```

The status should translate backend activity into clear consumer language without flooding the user with raw logs.

A future expandable Details view may expose technical errors when needed.

---

# 25. Bulk jobs use aggregate progress

For:

- YouTube bulk;
- YouTube playlists;
- direct bulk;

the main progress bar should represent aggregate progress for the whole job.

This is a locked decision.

The GUI should still display the currently active item title and queue position.

Example:

```text
● YouTube batch                         4 / 10
  Current Video Title

██████████████──────────── 56%

5.3 MB/s • 312 MB / 558 MB • ETA 00:47

Downloading item 4 of 10…
```

The progress bar should not simply reset and pretend the entire job is starting over for each new item.

---

# 26. Sequential bulk behavior

For sequential downloads:

- one item is active at a time;
- title changes as the active item changes;
- queue position updates;
- aggregate progress remains the primary progress bar.

Example:

```text
Direct batch                      4 / 10
linux.iso

████████████────────── 43%
```

This means:

- current item: 4 of 10;
- current title: `linux.iso`;
- whole batch: 43% complete.

---

# 27. Parallel bulk behavior

Parallel direct downloads create multiple simultaneous item progresses.

The main GUI should not show one arbitrary file's percentage as if it represented the whole batch.

For the first GUI, use aggregate telemetry.

Conceptually:

```text
total downloaded bytes across active/completed jobs
──────────────────────────────────────────────────
total known bytes across the batch
```

Example:

```text
Direct batch • 4 active • 10 total

███████████──────── 46%

22.4 MB/s • 3.1 GB / 6.8 GB
```

A future expandable per-item queue may be added later if real use justifies it.

It is not required for the first GUI.

---

# 28. Stream Inspector GUI behavior

Stream Inspector handoff should require minimal secondary interaction.

Example:

```text
● Browser-assisted HLS
  Spider-Man: Brand New Day

Subtitle detected

Save to
~/Videos                           [ Browse ]

                         [ Download ]
```

The extension has already performed browser-side intelligence.

The GUI should not force unnecessary choices afterward.

The same input field should support both normal URLs and Stream Inspector handoff text.

---

# 29. DownloadJob model

The GUI should not directly manipulate low-level downloader commands.

A shared internal job model is approved.

Conceptual flow:

```text
Input
  ↓
InspectionResult
  ↓
User choices
  ↓
DownloadJob
  ↓
AiDM core/router/downloader
```

The CLI and GUI should both ultimately describe a job to the same backend.

Conceptually:

```text
CLI interaction ─┐
                 ├→ DownloadJob → AiDM core
GUI interaction ─┘
```

This is one of the most important architectural decisions for the GUI.

---

# 30. DownloadJob should represent valid choices only

A DownloadJob should not imply that every workflow supports every option.

Examples:

## YouTube single

```text
source:
  youtube_single

url:
  ...

mode:
  video | original_audio | wav

destination:
  ...
```

`video_quality` is required for Video: a positive maximum height or explicit
`VideoQuality.BEST`. It must be absent for Original Audio and WAV. The model
validates this choice; Milestone 8 reveals the control only after explicit intent.

## YouTube bulk

```text
source:
  youtube_bulk

urls:
  [...]

mode:
  video | original_audio | wav

destination:
  ...
```

The same `video_quality` rule applies as for single video. Bulk discovers
qualities from the first normalized URL only, after Download/Enter and Video selection.

## YouTube playlist

```text
source:
  youtube_playlist

url:
  ...

video_quality:
  selected maximum height or explicit VideoQuality.BEST

destination:
  ...
```

No playlist audio mode in the first GUI.

## Direct bulk

```text
source:
  direct_bulk

urls:
  [...]

bulk_mode:
  sequential | parallel

destination:
  ...
```

This keeps the job model aligned with real backend capability.

---

## Milestone 7.3 implementation boundary

`download_job.py` provides a Qt-independent, frozen `DownloadJob` and
`build_download_job(result, *, destination, mode=None, video_quality=None, bulk_mode=None)`.
It reuses `InputKind`, copies URLs/subtitles into tuples and headers into a
read-only mapping, and rejects incompatible or missing choices with `ValueError`.
Milestone 9 adds required `destination: str`, normalized lexically as an absolute
path. Empty, relative or NUL-containing values are rejected. The Qt-independent
model does not probe directory existence or permissions; the GUI handles those
checks. The test helper automatically supplies the GUI's selected destination.
Milestone 10 consumes this snapshot for DIRECT_SINGLE execution only.

`YouTubeMode` supplies VIDEO, ORIGINAL_AUDIO and WAV for single/bulk video jobs.
ORIGINAL_AUDIO describes the CLI's existing `audio` mode. `video_quality` is a
positive maximum height, or explicit `VideoQuality.BEST` for the existing
best-available fallback. It is required for YouTube single/bulk VIDEO jobs and
playlists, including those underlying Inspector routes. `None` means a missing
required choice for these jobs, not an implicit fallback. Audio/WAV and unrelated
routes reject any supplied quality. Playlists still reject mode selections.
No quality availability lookup occurs in this builder.
`BulkMode` supplies SEQUENTIAL and PARALLEL for direct bulk. Choices have no
implicit defaults.

Inspector jobs retain their underlying `route_kind`, exact selected URL,
User-Agent/Referer, supplied title and ordered subtitles including duplicates.
Underlying YouTube routes still require their existing choices. Ordinary direct
single jobs have no pre-download title (Milestone 6.1); bulk counts are derivable
from URLs. Torrent is representable in the core model but remains deferred in GUI.
Metadata failure does not prevent creating an otherwise valid job.

The temporary `AiDMWindow.build_job_for_testing(...)` helper returns a snapshot
of the current classification without changing UI state or starting execution.
The F1–F7 previews remain available. Milestone 8 builds `download_job` from the
inline selections using the same builder, with no second GUI job model.

---

# 31. InspectionResult concept

The GUI needs a non-destructive way to ask the backend:

```text
What is this input?
What metadata is available?
What user choices are valid?
```

This suggests a conceptual InspectionResult layer.

Possible fields:

```text
InspectionResult
├─ kind
├─ title
├─ item_count
├─ available_modes
├─ available_playlist_qualities
├─ known_size
└─ additional metadata
```

A direct-single resolved filename is intentionally not part of pre-download
inspection. It belongs to runtime execution/telemetry once aria2c has resolved
the real output filename.

This is an architectural concept, not yet a locked implementation API.

The important behavior is that inspection must not start the actual download.

---

# 32. GUI capability must follow backend capability

Locked rule:

```text
GUI capability
must come from
backend capability
```

Not:

```text
GUI designer wants a control
→ backend is forced to grow a feature
```

Single/bulk video quality followed this sequence in Milestones 7.2–7.3;
GUI exposure follows the same sequence in Milestone 8:

```text
implement backend
→ test CLI
→ regression
→ expose in GUI
```

This protects scope and prevents the GUI project from becoming a hidden feature-expansion project.

---

# 33. Download options should disappear when the job starts

Configuration controls are useful only before execution.

Once the download begins, the UI should transition from configuration to active status.

For example, a YouTube job may move from:

```text
[ Video ] [ Original Audio ] [ WAV ]

Save to
~/Downloads              [ Browse ]

                    [ Download ]
```

to:

```text
● YouTube video
  Billionera – Otilia

██████████████──────────── 56%

5.3 MB/s • 312 MB / 558 MB • ETA 00:47

Downloading…

                          [ Abort ]
```

This keeps the active view clean.

---

# 34. Completion state

The GUI should not require a modal completion dialog.

A simple in-window completion state is preferred.

Example:

```text
✓ Download complete
```

A future action such as:

```text
[ Open Folder ]
```

may be useful.

The exact completion controls can be refined during implementation.

---

# 35. Failure state

Failure should be presented clearly without flooding the main view.

Conceptually:

```text
Download failed

[ Retry ]   [ Details ]
```

The main message should be human-readable.

Technical output may be exposed through a Details view if necessary.

This preserves useful debugging information without turning the primary GUI into a terminal emulator.

---

# 36. Abort behavior

During an active download, the primary action should change from Download to Abort.

Conceptually:

```text
[ Abort ]
```

Abort behavior must correctly terminate the active backend job without leaving unmanaged downloader processes.

The exact process-control implementation will need careful backend design.

---

# 37. Enter-key behavior

Keyboard behavior is part of the intended UX.

When READY:

```text
Enter
→ Download
```

The key should act as the primary Download action when appropriate.

Keyboard behavior for Abort should be treated more conservatively to avoid accidental cancellation.

---

# 38. UI technology direction

The leading candidate is PySide6 / Qt.

Reasons include:

- AiDM is already Python;
- natural integration with existing core logic;
- signals/events;
- asynchronous process handling;
- dynamic widgets;
- progress updates;
- keyboard shortcuts;
- native file dialogs;
- desktop integration;
- future system-tray potential;
- packaging support.

GTK remains technically possible, but PySide6 is the current preferred direction.

This is a design direction rather than an irreversible lock until implementation begins.

---

# 39. Packaging and desktop application behavior

A `.deb` package and a clickable graphical application are not competing ideas.

The desired long-term distribution is:

```text
AiDM package
     │
┌────┴─────┐
│          │
CLI       GUI
│          │
└── AiDM core
```

A Debian package can install:

- executable(s);
- Python application files;
- desktop launcher;
- application icon;
- required metadata.

Conceptually:

```text
/usr/bin/aidm
/usr/lib/aidm/...
/usr/share/applications/aidm.desktop
/usr/share/icons/.../aidm.png
```

The user should eventually be able to:

- run AiDM from the terminal;
- click AiDM from the Linux application menu;
- receive the same core behavior through either frontend.

Packaging should happen after the GUI is working and tested.

Recommended sequence:

```text
GUI architecture
↓
working GUI
↓
real tests
↓
desktop entry/icon
↓
.deb packaging
```

---

# 40. First GUI scope

The first GUI is intentionally not an opportunity to expand every AiDM feature.

Primary goals:

- graphical frontend for current mature CLI capabilities;
- flexible minimal layout;
- non-destructive input inspection;
- inline job-specific options;
- destination selection;
- live progress;
- truthful backend telemetry;
- status language;
- aggregate bulk progress;
- DownloadJob abstraction;
- Stream Inspector compatibility;
- continued CLI independence.

Not required for the first GUI:

- further YouTube quality capabilities beyond the verified maximum-height selection;
- playlist audio support;
- full torrent UI;
- giant per-item queue dashboard;
- custom frameless window system;
- native messaging with Stream Inspector;
- backend feature expansion unrelated to GUI needs;
- replacing the CLI.

---

# 41. Core invariants

The following invariants should be protected throughout GUI development.

## Invariant 1

```text
main remains the authoritative mature baseline
```

## Invariant 2

```text
CLI and GUI share backend intelligence
```

## Invariant 3

```text
GUI functionality does not exceed proven CLI/backend functionality
```

unless a new backend feature is intentionally developed and validated first.

## Invariant 4

```text
progress shown in GUI must come from real backend telemetry
```

## Invariant 5

```text
Stream Inspector handoff grammar remains shared
```

## Invariant 6

```text
the GUI should progressively reveal controls instead of permanently displaying irrelevant options
```

## Invariant 7

```text
new GUI work must not break mature CLI workflows
```

---

# 42. Target user experience

The intended final feeling is:

```text
paste something
↓
AiDM understands it
↓
show only the choices that matter
↓
choose destination
↓
press Enter or Download
↓
watch truthful live progress
↓
see understandable backend status
↓
download completes
```

The UI should remain small.

The intelligence should remain large.

That is the central design identity of the AiDM GUI.
