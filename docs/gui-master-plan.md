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

StatusEvent answers **what is happening**. ProgressEvent, introduced in
Milestone 12, answers **how far it has progressed**. No progress fields, parsing,
filename discovery or artificial finalization stage belong in StatusEvent.
Inspection/configuration statuses and the CLI renderer remain unchanged.

## Milestone 12 direct-single telemetry

Only DIRECT_SINGLE aria2c execution emits progress. The path is:
`aria2c stdout → Aria2ProgressParser → ProgressEvent → GUI presentation`.
The frozen, Qt-independent ProgressEvent contains independently optional
`percent`, `downloaded_bytes`, `total_bytes`, `speed_bytes_per_second`, and
`eta_seconds`. Values must be non-negative (percent 0–100); missing values are
valid. No title/filename extraction or additional execution route is introduced.

`build_direct_command(..., telemetry=True)` opts the GUI into full, uncolored
console readouts with exact byte counts using `--show-console-readout=true`,
`--enable-color=false`, `--truncate-console-readout=false` and
`--human-readable=false`. The existing `--summary-interval=1` is retained.
CLI callers omit telemetry and retain their existing flags and cwd output.

The isolated backend parser is verified against installed aria2c 1.37.0 local
HTTP captures in `tests/fixtures/aria2/`. It frames arbitrary stdout chunks across
CR/LF delimiters, flushes complete trailing records on exit, bounds its buffer,
and ignores unrelated/malformed lines. It accepts exact B values and binary
KiB/MiB/GiB readouts; fractional human-readable values are truncated to integer
bytes after conversion. `DL` represents bytes/second. ETA h/m/s becomes seconds.
Aria2's `/0B` unknown-total sentinel becomes None. Percent is used only when
reported, never inferred from time or forced to 100 on success.

The GUI shows a 0–100 bar only when a real percent is available, truncating its
display to integer percent while retaining event precision. Below it, a compact
statistics label uses decimal SI units (1000 B = 1 KB), up to one decimal place,
and MM:SS or H:MM:SS ETA. Unknown components are omitted. Each event replaces the
current snapshot, so a missing ETA/percent cannot leave stale values visible.
StatusEvent independently supplies the activity text beneath these metrics;
ProgressEvent never transitions GuiState.

Completion and failure retain the last real snapshot, even if below 100%; a
successful exit does not manufacture telemetry. Input changes, new jobs and
development state resets clear the snapshot. Late events from an old process
are ignored. No user-facing Abort, retry or progress support for other routes
is included.

## Milestone 13 active-download presentation

`GuiState.DOWNLOADING` replaces configuration with a compact active view:
heading, classification, genuine title if available, real progress when known,
compact statistics and current StatusEvent activity. The input is hidden without
clearing its text; destination, Browse, Download and all secondary options are
hidden. Existing active-job mutation guards remain in force. DIRECT_SINGLE has
no guessed title/filename. Missing title or telemetry leaves no placeholder.

The native, text-visible progress bar uses the system palette. Unknown percent
hides the bar while available statistics and activity remain visible. Statistics
retain the Milestone 12 formatter and wrap at narrow widths. On entering active
or terminal states, the window height fits the content without animation; width
is preserved. Progress updates do not explicitly resize the window.

COMPLETE and FAILED hide active progress/statistics and show the existing clear
result message. The last real ProgressEvent remains unchanged internally; no
100% event is manufactured. Input returns for subsequent editing. StatusEvent,
ProgressEvent and GuiState retain their separate responsibilities. Abort remains
hidden and disabled until Milestone 14; no execution behavior changes here.

## Milestone 13.1 direct runtime filename

DIRECT_SINGLE still has no pre-download title or URL-derived filename. During
execution, explicit aria2c `FILE: /path/name.ext` records supply the resolved
basename through `DirectDownloadProcess.filename_resolved`. The existing bounded
CR/LF stdout framing handles split records; complete lines use the filesystem
encoding with replacement for invalid bytes. Repeated names are suppressed by
the adapter. Completion tables are not a filename source.

The active plain-text title area prefers a genuine inspection title, then the
runtime direct filename, otherwise stays hidden. No filename is added to
ProgressEvent or StatusEvent. Input changes, new execution and development resets
clear runtime identity; stale/non-active process signals are ignored. Terminal
presentation remains unchanged, with the runtime name retained only internally.

## Milestone 14 shared Abort and Retry lifecycle

`DownloadProcess` owns one QProcess attempt, lifecycle signals, capability flags
(`can_abort`, `can_retry`), termination and cleanup. Engine adapters supply the
command and stdout interpretation. `create_download_process(job, parent)` is the
central execution boundary; only DIRECT_SINGLE currently maps to a real adapter.
Unsupported routes remain deferred. The GUI's start/Abort/Retry flow is route
neutral, tested with a non-direct fixture adapter as well as aria2's adapter.

Interactive Abort marks intent, emits `StatusKind.ABORTING` ("Aborting…"), disables
Abort, sends terminate and starts a single-shot 2500 ms grace timer. If still
active it sends kill; only process finish declares the typed terminal outcome.
No interactive waitForFinished is used. User abort wins over an exit code, while
FailedToStart remains FAILED. `ExecutionOutcome` controls GuiState independently
of status wording: COMPLETE, FAILED or ABORTED. ABORTED displays "Download aborted".
Telemetry/filename updates are ignored once Abort is requested. Terminal states
hide active telemetry and Abort. Failed/aborted retryable attempts show Retry;
success does not. Enter remains Download-only while READY.

Retry keeps the exact immutable attempted DownloadJob, revalidates its destination
and obtains a fresh adapter from the factory. It does not classify again or read
mutable configuration. Missing destination blocks retry without redirecting it.
Each attempt clears status, progress and runtime filename. All process signals
check sender identity and active GUI state; late old-attempt signals are ignored.
Input edits/development resets discard retry context. F1–F7 keep their existing
preview mapping and cannot interrupt an active attempt.

AiDM does not implement resume or inspect, edit, rename or delete partial files
or `.aria2` state. The direct adapter keeps the same URL/destination and existing
`--continue=true`; aria2 decides whether reusable state permits resume. A fresh
attempt may truthfully report a nonzero first percentage.

Close-time cleanup remains bounded terminate/wait/kill/wait, stops the escalation
timer and suppresses terminal UI signals while closing. If reaping fails, the
window retains ownership instead of abandoning the process. This common policy
owns the current QProcess; future multi-process adapters must account for their
additional children without duplicating the GUI lifecycle. No additional engine
execution, pause or manual resume is introduced.

## Milestone 14.1 GUI tone and terminal emphasis

GUI-rendered activity, inspection, warnings and outcomes use restrained emoji
cues. Structural route labels, filenames, metrics and action buttons remain
undecorated. Emoji supplements understandable text, never replaces meaning;
backend event values and lifecycle semantics are unchanged.

COMPLETE, FAILED and ABORTED use a centered, bold 20-point plain-text result
with vertical padding and wrapping. Retry is centered immediately below failed
or aborted retryable outcomes; success has no Retry. Active status keeps its
normal smaller font. Existing input/identity presentation and lifecycle remain
intact. Fonts and colors use the system; no emoji font, custom color palette,
rich text or new dependency is introduced. Monochrome/platform-specific emoji
rendering is acceptable.

## Milestone 14.2 terminal identity retention

Terminal states retain the same genuine identity used during execution:
inspection title first, runtime-resolved filename second, otherwise no title.
The hierarchy is classification → title → terminal outcome → Retry when eligible.
Terminal titles are centered, bold 13-point plain text, below the 20-point result
banner in emphasis. Long terminal names elide in the middle within the available
width, preserving the full identity internally and in a tooltip. Active title
styling is unchanged. Retry clears runtime
identity for the new attempt as before. No URL fallback, parsing or metadata
request is introduced; identity presentation is route neutral.


## Milestone 15 single YouTube execution

The factory now executes **DIRECT_SINGLE and YOUTUBE_SINGLE only**. Single
YouTube Video, Original Audio and WAV use `YouTubeDownloadProcess` and the same
`DownloadProcess` attempt lifecycle, GUI dispatch, Abort/Retry, stale-signal
protection, genuine title and terminal presentation. Bulk, playlists, Inspector
handoffs and other routes remain deferred, even when their underlying route is
YouTube. No GUI lifecycle is duplicated.

Shared `youtube.py` builders own format selection, aria2 handoff and output policy.
Positive `video_quality` is consumed as the chosen maximum height; BEST maps to
`None`, with no rediscovery. Video keeps resolution-first MP4/M4A preference and
MP4 merge/remux without video transcoding. Original Audio keeps `bestaudio/best`;
WAV uses the existing extraction/conversion flags. GUI execution supplies `-P`
with the immutable destination and `--no-playlist`. CLI defaults, prompts,
playlist/bulk behavior and cwd behavior remain unchanged.

GUI-only telemetry uses yt-dlp JSON progress/postprocessor templates with AiDM
sentinels. Native byte counts yield current-stream percent only with an exact
positive total. Estimated totals are intentionally omitted. Optional fields stay
optional. Installed yt-dlp's external aria2 downloader reports structured progress
only at stream completion, so live external metrics reuse the strict aria2 parser
with GUI-only exact-byte/uncolored summary flags. Captured local-media fixtures
in `tests/fixtures/ytdlp/` verify both paths. The parser owns bounded CR/LF framing;
the GUI still consumes only StatusEvent and ProgressEvent.

Video and audio are separate transfers: percentage can restart between them; it
is not aggregate whole-job progress. Codec fields identify native video/audio
phases when known; external video-mode readouts use generic Downloading rather
than guessing the stream. Real postprocessor-start hooks describe merging, audio
conversion, remuxing and finalization. Transfer metrics clear at those stages.
Only successful yt-dlp process exit declares COMPLETE, never a stream's 100%.

The shared lifecycle optionally owns a Linux process session using Qt 6.7+
CreateNewSession. The YouTube adapter enables it so ordinary yt-dlp descendants
(aria2c and FFmpeg, which inherit the group) receive group TERM, then group KILL
if still running after the existing 2500 ms Abort grace period. Parent exit does
not finish an attempt while live group children remain. Cleanup polls without
blocking interactive Abort; close-time cleanup is bounded and retains ownership
if stopping fails. QProcess reaps its parent process; orphaned exited descendants
are left to the OS reaper, and Linux zombie entries do not count as running.
No global-name kill commands or shell invocation are used. This tree ownership
currently targets Linux, not speculative Windows/macOS adapters.

Retry reuses the exact immutable job in a fresh adapter, including mode, quality,
title and destination. The GUI neither implements resume nor deletes partial
state. yt-dlp/aria2c/FFmpeg retain their mature continuation and postprocessing
behavior. Live YouTube extraction/authentication and real-world Abort/Retry remain
part of the manual three-mode acceptance checks.


## Milestone 16 YouTube bulk execution and shared batch presentation

The execution factory now supports DIRECT_SINGLE, YOUTUBE_SINGLE and
YOUTUBE_BULK. All other routes, including YouTube playlists and direct bulk,
remain deferred. Single and bulk YouTube reuse `YouTubeDownloadProcess`: bulk
passes all immutable job URLs, in order, to one yt-dlp invocation and one owned
process group. Video consumes the already-selected maximum height/BEST and keeps
MP4 merge/remux policy; Original Audio keeps `bestaudio/best`; WAV uses the same
existing extraction/conversion path. There is no new discovery or mode UI.
Destination, Abort, close cleanup, failure handling and same-job Retry are shared.

`BatchEvent` is frozen and Qt-independent: validated `current_index`,
`total_items`, optional `title`, optional `aggregate_percent`. It contains no
transfer metrics. StatusEvent describes activity, ProgressEvent describes the
current transfer, and BatchEvent describes queue position and aggregate progress.
The generic `batch_event` channel and GUI renderer are reusable by future routes.

GUI telemetry uses `before_dl:AIDM_ITEM:%(.{video_autonumber,title})j`; normal CLI
bulk retains its human `[i/N] Starting download: title` output. The bounded yt-dlp
parser produces normalized ItemStarted records. The adapter validates the index
against `len(job.urls)`, never an output-supplied total. Captured yt-dlp 2026.08.19
local HTTP runs verify 1/2/3 item numbering, mode sequencing and item-start records
when already-completed files are revisited. Failures before item-start supply no
identity; no missing title/index is guessed. Nonzero process exit remains FAILED.

The active layout is classification → compact `2 / 10` → current genuine title →
one aggregate bar → current-transfer statistics → backend activity → Abort.
Runtime item titles replace generic/first-item inspection identity and render as
plain text. No item list or per-item bars are introduced. Generic DOWNLOADING
renders `Downloading item 2 of 10…`; observable merge/audio/conversion activity
keeps its existing short wording, with queue position visible independently.

The main bar is **item-weighted**, not byte-weighted:
`100 * ((current_index - 1) + current_item_percent / 100) / total_items`.
Without known current percent, the baseline is `100 * (current_index - 1) / N`.
`SequentialBatchProgress` retains the highest contribution within/across phases,
so audio resets and postprocessing cannot move the batch bar backward. Duplicate
item-start records do not reset progress; backward/out-of-range starts are ignored.
New item starts clear stale current-stream metrics, while aggregate progress stays.
Statistics (speed, bytes, ETA) always refer to the current item/stream, not the batch.

A stream's 100% contribution is not item/job completion: queue advancement is
backend workflow evidence, and terminal success still requires successful overall
process exit. Consequently the last item's bar may reach 100% during processing
while the status remains active. Success may emit aggregate 100% as job-state
truth; it never fabricates or changes ProgressEvent. Failure/Abort do not force
aggregate completion. Terminal states hide active telemetry and retain the last
known item identity internally; Milestone 16.1 defines the terminal summary below.

Every new attempt clears batch identity/progress, including Retry; no previous
index is assumed. Retry sends the same URLs/mode/quality/destination to a fresh
adapter and follows actual item events as yt-dlp skips or resumes existing output.
Input edits and development resets clear batch presentation. Sender/active-attempt
checks reject stale batch signals just like existing status/progress signals.
AiDM neither deletes partial state nor implements custom per-item resume.

## Milestone 16.1 batch presentation polish

Active queue position uses a shared 14-point bold label, above the changing
current-item title and below the terminal banner in prominence. Execution and
BatchEvent/progress semantics are unchanged.

Terminal multi-item states hide the last active title and ordinary item-count
line. COMPLETE instead displays a centered, bold 14-point aggregate summary
above the existing 20-point result banner: `4 videos downloaded` or
`4 files downloaded`. YouTube bulk/playlist use video(s), direct bulk uses file(s),
and other batch routes default to item(s), with correct singular/plural wording.
For URL-list bulk jobs the attempted immutable DownloadJob URL count is authoritative;
playlist-sized summaries use reliable inspection item_count, never a one-URL
playlist length or the last BatchEvent. Unknown counts produce no summary.
FAILED and ABORTED show their existing outcome/Retry group without claiming a
completed-item count. Single-job terminal title/runtime-filename retention remains
unchanged. This does not enable playlist or direct-bulk execution.

## Milestone 17 YouTube playlist execution

`YOUTUBE_PLAYLIST` now uses the existing `YouTubeDownloadProcess` and shared
execution factory. It remains VIDEO-only: the configured maximum height or
explicit BEST is consumed without rediscovery. CLI and GUI share
`build_youtube_playlist_command`: existing video format/MP4 merge/remux policy,
aria2 handoff, `--yes-playlist`, and GUI-only `-P` destination/telemetry options.
Default CLI commands and interactive quality selection remain unchanged.

The immutable DownloadJob now preserves optional positive `item_count` for a
collection URL. Inspection's known playlist count is authoritative, never
`len(job.urls)` (one playlist URL). URL-list bulk continues using its URL count.
If inspection did not return a count, the first valid runtime `n_entries` may
initialize batch progress; no count is invented. Until a batch total is known,
no aggregate bar or completed-count summary is shown.

Playlist `before_dl:AIDM_ITEM` JSON uses `playlist_autonumber` (download queue
position), `n_entries`, and `title`. The field semantics were verified in the
installed yt-dlp 2026.08.19 source and by processing an offline three-entry
playlist with `skip_download`; this is template evidence, not a real YouTube
transfer. Known snapshot counts are not overwritten by runtime output. Playlist
changes between inspection and execution can make the snapshot stale; indices
outside its range are ignored rather than expanding or fabricating the count.

Active identity is now:

```text
classification
playlist/job title (16-point bold, stable primary identity)
current / total (existing 14-point bold queue label)
current video title (13-point bold, changing secondary identity)
aggregate progress
current item/stream statistics
StatusEvent activity
Abort
```

Both identity labels remain plain text, fit the available width, and retain full
text in tooltips. Current item records never overwrite inspection/job title.
The existing BatchEvent / SequentialBatchProgress item-weighted formula and
high-water contribution prevent regressions between video/audio phases. No
byte-weighted estimates or new lifecycle are introduced.

On COMPLETE, the current video title disappears; playlist title remains above
the centered bold summary `YouTube playlist downloaded • N videos` (or `1 video`)
and `Download complete 🎉💫`. FAILED/ABORTED retain playlist title and Retry,
hide the current video title, and make no completed-count claim. Ordinary bulk
keeps its single active-title level and `N videos downloaded` terminal summary.

Abort, process-group cleanup, terminal outcomes, stale-attempt guards, and Retry
are inherited unchanged. Retry creates a fresh adapter for the same immutable
URL/quality/destination/title/count snapshot. yt-dlp/aria2 own skip/resume behavior;
AiDM does not delete partials. Direct bulk, HLS/DASH, Stream Inspector and other
deferred execution routes remain deferred.


## Milestone 18 direct bulk execution

The factory now also executes `DIRECT_BULK` using `DirectBulkDownloadProcess`
with the existing explicit `BulkMode.SEQUENTIAL` / `BulkMode.PARALLEL` choice.
DIRECT_SINGLE and all three implemented YouTube routes retain their adapters.
HLS/DASH, Inspector, generic yt-dlp and torrent execution remain deferred.
The immutable DownloadJob, common DownloadProcess lifecycle, Abort/Retry,
terminal outcomes and route-neutral frontend dispatch are reused.

Shared command policy lives in `downloader.py`. Sequential uses
`build_direct_command`; parallel GUI and CLI use
`build_direct_bulk_parallel_command`. CLI flags, tuning, prompts, success text,
blocking wrappers and cwd behavior are unchanged. GUI passes the snapshot
`--dir=<destination>`; it never changes cwd or calls a blocking CLI wrapper.
The existing exact-byte, uncolored, untruncated GUI telemetry flags stay opt-in.
Only GUI parallel additionally uses `--console-log-level=notice` to observe live
completion facts; these messages are parsed internally, not shown as UI text.

**Sequential locked presentation:** classification → current index / total →
current runtime filename → item-weighted aggregate bar → current-item statistics
→ `Downloading item i of N… ⬇️` → shared Abort.
The controller starts one aria2 invocation per URL in original order, reusing
one QProcess only after its previous invocation finishes. Index comes from the
controller. Filename comes exclusively from runtime `FILE:` records, with no URL
fallback. New items clear the previous name and statistics. Existing
`SequentialBatchProgress` computes `100 * (completed_items + current_fraction) / N`,
or the completed baseline when percent is unknown; its high-water value never
regresses. Speed, bytes and ETA remain current-item metrics. The first nonzero
exit stops the batch. Advancement is queued through a zero-delay Qt timer, with
Abort/closing checks before launching the next item, including synchronous
signal callbacks at the handoff boundary.

**Parallel locked presentation:** classification →
`N files • X active • Y complete` → aggregate bar → aggregate statistics →
`Downloading in parallel… ⚡` → shared Abort. There is no current index/title,
no changing filename, and no per-item list. `ParallelBatchEvent` is a separate
small frozen contract on the existing batch-event channel, so sequential fields
are never overloaded. Frontend presentation depends on that structured state,
not direct-bulk/mode checks. `ParallelBatchProgress` is Qt/engine-independent and
must remain reusable by future workflows.

Parallel retains the mature single-aria2 strategy: an input file containing the
exact URL list and `--max-concurrent-downloads=N`. Its TemporaryDirectory belongs
to the adapter for the full asynchronous attempt. It is removed only after exit,
failed startup, Abort reaping, or successful close cleanup; preparation errors
also fail cleanly and release it. The input file is not a resume database.

`Aria2ParallelProgressParser` reuses bounded CR/LF framing and strict single-GID
metric parsing. Local aria2c 1.37.0 captures in `tests/fixtures/aria2/parallel*.txt`
verify simultaneous GIDs, exact bytes, FILE records, completion while other
transfers continue, and final results. Whole detailed summary blocks replace
the active GID set. Compact `[DL:...]` readouts are ignored because captured
values can include recently completed transfers. A completion notice is matched
to a GID through its exact runtime FILE path; final `OK` result rows also prove
item success. Neither 100% nor disappearance from an active summary proves
completion. Overall normal exit 0 confirms all N items; any nonzero/crashed exit
is FAILED even if some files finished.

Parallel aggregate policy:

- Use byte weighting only when totals for **all N items** are known.
- Otherwise use `(completed_count + sum(active_known_fraction)) / N`.
  Unknown/not-started items contribute zero; completed items contribute one.
- Keep the highest backend-derived aggregate through incomplete/reordered
  updates and transitions between weighting policies. A transfer's 100% alone
  never changes the completed counter or terminal lifecycle.
- Sum speeds from the latest active snapshot, excluding completed items. If an
  active speed is unknown, omit aggregate speed rather than imply completeness.
- Sum observed downloaded bytes, retaining completed items. Known-size completed
  items contribute their full size; unknown-size items retain their last observed
  byte lower bound. Show `downloaded / total` only when the whole total is known;
  otherwise show `X downloaded`. No size prefetch or filesystem-size guessing.
- Omit parallel ETA entirely. Individual ETAs are not a batch ETA.

Telemetry is periodic, so live counts may lag by a summary interval. A very fast
or already-satisfied item can finish before any GID/FILE summary; an unmatched or
ambiguous completion path waits for its GID result row or successful process exit.
Unknown-length transfers may leave a conservative downloaded-byte lower bound.
These cases never invent identity, size or completion. Long malformed records
are bounded/discarded; telemetry limitations do not change exit-code authority.

Both modes reuse the existing terminal summary helper: `1 file downloaded` /
`N files downloaded`, then `Download complete 🎉💫`. FAILED/ABORTED hide all item
identity/count claims and show the shared outcome plus Retry. Retry creates a
fresh adapter for the **same immutable job** (URLs, mode, destination), resets
attempt telemetry and starts from the original input list. aria2 owns skipping,
continuation and `.aria2` state; AiDM deletes no partial download files.

Local manual checks (from the repository root):

```bash
python3 tests/fixtures/aria2/serve_bulk.py
```

In another terminal:

```bash
mkdir -p /tmp/aidm-m18-sequential /tmp/aidm-m18-parallel
python3 aidm_gui.py
```

Paste the server's four URLs, choose Sequential and the sequential destination.
Expect positions 1/4 through 4/4, names `runtime-1.bin` through `runtime-4.bin`
from aria2 (different from URL names), a monotonic aggregate, and current-item
statistics. On fresh files, Abort during item 2 must stop aria2 and prevent item 3
from starting; Retry repeats the same job and lets aria2 resume. Let it finish:
`4 files downloaded` and the shared success banner, without a last filename.

Repeat with Parallel and its separate fresh destination. Add `/5.bin` and
`/6.bin` to exercise six files. Expect active/completed counts, summed speed,
whole-batch bytes only once all totals are observed, and no filename/index/ETA.
Abort while multiple files are active, verify the owned aria2 process exits,
then Retry and finish. Use `/4.bin?unknown=1` in a fresh folder for unknown-total
fallback: downloaded-only bytes and item-weighted progress. Replace a URL with
`/missing.bin` for failure; no success-count summary should appear. Stop the
fixture server with Ctrl+C afterward.

Automated regressions:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -p 'test_direct_bulk_execution.py'
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests
```

These are offline model/parser/CLI-contract and Qt lifecycle/presentation tests;
real local QProcess/aria2 transfers are validated separately. Interactive desktop
appearance and remote-server behavior remain manual acceptance checks.

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

Sequential batches display the currently active item title and queue position.
Parallel batches show total/active/completed counts without a current item.

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
total bytes only when known for every batch item
```

Example:

```text
Direct batch
10 files • 4 active • 3 complete

███████████──────── 46%

22.4 MB/s • 3.1 GB / 6.8 GB
```

When any item total is unknown, use the Milestone 18 item-weighted fallback
and downloaded-only bytes. Sum current active speeds; omit aggregate ETA.

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

Milestone 21 implements the centered in-window success presentation:

```text
Download complete 🎉💫

[ Open Folder ]
```

Existing single, batch, playlist, and Inspector terminal identities remain intact.
Open Folder appears only in COMPLETE and targets the completed attempt's immutable
`DownloadJob.destination`, using Qt native folder opening. It never auto-opens,
uses a runtime filename, or reads the mutable destination selector.

The destination must still exist as a directory. An unavailable directory or a
native opening failure shows a small non-terminal warning; COMPLETE and its
success message remain intact. No fallback folder is opened or recreated.
New input and new attempts hide the action and clear its warning.

---

# 35. Failure state

Failure should be presented clearly without flooding the main view.

Conceptually:

```text
Download failed

[ Retry ]
```

The main message should be human-readable.

FAILED and ABORTED retain the existing Retry action and immutable-job retry semantics.
Details diagnostics remain deferred beyond Milestone 21.

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
