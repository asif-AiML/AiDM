# AiDM Advanced Download Controls — Design Notes

> **Status:** Draft / discussion document  
> **Branch:** `feat/controls-settings`  
> **Purpose:** Define safe, GUI-friendly control over selected yt-dlp and aria2c behavior before implementation.

---

## 1. Goal

AiDM already hides the complexity of its underlying engines:

- `aria2c`
- `yt-dlp`
- FFmpeg where required

The next feature should give users more control over download behavior **without requiring them to understand engine flags or command-line syntax**.

The GUI should expose useful concepts such as:

- speed;
- connection count;
- parallelism;
- retry behavior;
- HLS/DASH fragment concurrency;
- bandwidth limiting.

The user should interact with simple controls while AiDM translates those choices into safe backend flags.

The guiding principle is:

```text
GUI-friendly setting
        ↓
AiDM translates it
        ↓
appropriate yt-dlp / aria2c flags
```

The GUI should not become a visual copy of the yt-dlp or aria2c manuals.

---

## 2. Settings location

These controls should **not** clutter the main download screen.

Add a small gear/settings icon near the top of the application.

Conceptually:

```text
AiDM                                      ⚙
```

Opening it reveals a dedicated settings surface with room for future options.

A possible structure:

```text
Download profile
[ Balanced ▼ ]                     ⓘ

PERFORMANCE

Connections per file
[ 4 ▼ ]                            ⓘ

Parallel files
[ 4 ▼ ]                            ⓘ

Stream fragments
[ 4 ▼ ]                            ⓘ


BANDWIDTH

Speed limit
[ Unlimited ▼ ]                    ⓘ


RELIABILITY

Retry attempts
[ 10 ▼ ]                           ⓘ

Stream fragment retries
[ 10 ▼ ]                           ⓘ


[ Restore Defaults ]
```

This is only a design direction. Exact layout and controls are not yet locked.

---

## 3. Information buttons

Every exposed setting should have an `ⓘ` information control.

The purpose is to explain the setting in **plain English**, especially for users who do not know yt-dlp or aria2c.

The information text should explain:

1. what the setting changes;
2. what increasing/decreasing it usually does;
3. when it may help;
4. possible trade-offs or risks;
5. whether the setting is generally safe.

Example:

```text
Connections per file

ⓘ Downloads different parts of one file at the same time.
   Higher values may improve speed on large files, but some
   servers restrict multiple connections.
```

The tooltip should avoid unnecessary backend jargon.

It should also state **where the setting actually takes effect**.

A user must never assume that every yt-dlp-related setting affects every job that happens to involve yt-dlp. AiDM often uses yt-dlp only for extraction/selection and then hands the actual transfer to aria2c.

Example:

```text
Concurrent stream fragments

ⓘ Affects browser-assisted HLS/DASH downloads where yt-dlp's
   native fragment downloader transfers the media.

   It does not affect direct downloads or normal YouTube jobs
   that AiDM hands to aria2c.
```

Likewise, aria2c controls should say that they apply to jobs where aria2c performs the transfer.

Advanced users may optionally see the underlying engine option in smaller secondary text later, but that is not required for the first version.

---

## 4. Recommended / best choice guidance

A tooltip alone is not enough.

A user may understand what a setting does but still have no idea which value to select.

Therefore option lists should clearly mark one or more meaningful choices.

Possible labels include:

- `Recommended`
- `Balanced`
- `Best performance`
- `Conservative`
- `Advanced`

Example:

```text
Connections per file

1 — Conservative
2
4 — Recommended
8 — Best performance
```

The exact wording and values must be validated before implementation.

Important distinction:

- **Default** means what AiDM starts with.
- **Recommended** means the safest general-purpose choice for most users.
- **Best performance** means the strongest generally useful performance-oriented choice tested by AiDM, not a guarantee that it will always be fastest.

A user with no technical knowledge should be able to safely choose the marked recommendation without researching engine flags.

The GUI should never imply that a higher number is always better.

---

## 5. Preset/profile idea

A higher-level download profile may sit above individual controls.

Possible concept:

```text
Download profile

● Balanced
○ Conservative
○ Fast
○ Custom
```

Possible meanings:

### Conservative

- fewer simultaneous connections;
- low fragment concurrency;
- lower parallelism;
- maximum compatibility/reliability.

### Balanced

- moderate parallelism;
- safe general-purpose defaults;
- intended default profile.

### Fast

- higher but still tested concurrency;
- intended for users who want stronger performance and have a stable connection/server.

### Custom

- user directly controls the individual values.

The exact numeric values are **not locked yet**.

They should be based on testing rather than assuming that higher values automatically mean higher speed.

---

## 6. Important aria2c controls

### 6.1 Connections per file — LOCKED DESIGN

Relevant aria2c options:

```text
--split
--max-connection-per-server
```

These two options are treated as **one user-facing control**.

The GUI must not expose them as two independent settings.

Friendly control:

```text
Connections per file
```

When the user selects a numeric value `N`, AiDM should apply the corresponding aria2c connection policy together:

```text
--split=N
--max-connection-per-server=N
```

This prevents confusing combinations such as:

```text
--split=8
--max-connection-per-server=1
```

where the GUI claims a high connection setting but aria2c is still limited to one connection per server.

#### Locked choices

The first version should expose:

```text
Auto — Recommended
1 — Maximum compatibility
4 — Balanced
8 — Best performance
```

Do not expose `16` in the first version.

The goal is to provide useful control without encouraging excessively aggressive connection counts.

#### Auto — Recommended

`Auto` does **not** mean random or adaptive benchmarking.

It means:

```text
preserve AiDM's proven route-specific connection defaults
```

Current proven behavior:

```text
Direct single
Direct bulk sequential
Direct bulk parallel
    → 1 connection per file

Normal YouTube transfers delegated to aria2c
    → 8 connections per file
```

This is the default and recommended choice because enabling the new Settings feature must not silently change already-tested download behavior for users who never touch the setting.

#### 1 — Maximum compatibility

Meaning:

```text
one file
→ one connection
```

Expected behavior:

- least aggressive;
- generally safest with restrictive servers;
- useful when higher connection counts cause failures or throttling;
- may be slower when a server limits throughput per connection.

#### 4 — Balanced

Meaning:

```text
one file
→ up to four simultaneous pieces/connections
```

Expected behavior:

- moderate segmented downloading;
- useful manual choice for users who want additional speed without using the strongest exposed setting;
- may improve throughput on large files;
- still depends on server and network behavior.

#### 8 — Best performance

Meaning:

```text
one file
→ up to eight simultaneous pieces/connections
```

Expected behavior:

- strongest performance-oriented value exposed by AiDM in the first version;
- can improve throughput when a server benefits from parallel connections;
- is **not** a promise that every download will be faster;
- some servers may restrict, throttle or reject multiple simultaneous connections.

The label `Best performance` means:

> the strongest generally useful performance-oriented setting intentionally exposed by AiDM,

not:

> universally guaranteed fastest value for every server.

#### Why 16 is intentionally omitted

Higher values can create diminishing returns and much larger total connection counts when combined with parallel bulk downloading.

Example:

```text
6 parallel files × 16 connections per file
≈ up to 96 simultaneous connections
```

That is unnecessarily aggressive for a beginner-facing first version.

The safe first-version ceiling is therefore:

```text
8 connections per file
```

#### Internal minimum split size

Current AiDM uses:

```text
--min-split-size=1M
```

This should remain an internal implementation detail for now.

Do not expose it as a separate GUI control in the first version.

#### Applicability

This control applies only when **aria2c is actually transferring the bytes**.

Applies to:

```text
Direct single                         yes
Direct bulk sequential                yes
Direct bulk parallel                  yes
Normal YouTube transfer via aria2c    yes
Other aria2c-backed media transfers   yes
```

Does not apply to:

```text
yt-dlp-native browser-assisted HLS/DASH fragment transfer
```

The fact that yt-dlp participates in a route does not automatically make yt-dlp the transfer engine.

#### Locked information text

The first-version `ⓘ` explanation should communicate:

```text
Connections per file

Controls how many parts of one file aria2c can download at the
same time. More connections can improve speed when a server
limits each connection, but some servers restrict multiple
connections.

Auto — Recommended keeps AiDM's tested setting for each
download type. 1 offers maximum compatibility, 4 is balanced,
and 8 is the performance-oriented choice.

This setting applies only when aria2c performs the download.
It does not affect native HLS/DASH streams downloaded by
yt-dlp.
```

The wording may be polished during final GUI implementation, but the meaning above is locked.

#### Testing requirement

A long benchmark session is **not required** for this control.

Because `8` is already used successfully in AiDM's established aria2-backed YouTube path, the main new validation needed later is a short direct-download sanity test.

Suggested implementation-phase check:

```text
same stable large direct URL

1 connection  → run briefly
4 connections → run briefly
8 connections → run briefly
```

About 30–45 seconds per run is sufficient.

The goal is not to prove universal speed rankings.

The goal is only to verify:

- segmented downloading works;
- each value is actually passed to aria2c;
- no obvious failure appears;
- higher settings remain operational and sane.

Full-file completion is not required solely for validating this setting.

---

### 6.2 Parallel files

Relevant aria2c option:

```text
--max-concurrent-downloads
```

This controls the number of separate files aria2c downloads at the same time.

It is particularly relevant to:

```text
Direct bulk → Parallel
```

Friendly setting:

```text
Parallel files
```

Example:

```text
20 files total
4 parallel files

→ 4 active
→ remaining files wait
```

This is different from connections per file.

Both values interact.

For example:

```text
4 parallel files × 8 connections per file
≈ up to 32 simultaneous connections
```

AiDM must avoid unsafe combinations and should warn or constrain settings when necessary.

---

### 6.3 Global bandwidth limit

Relevant aria2c option:

```text
--max-overall-download-limit
```

Friendly setting:

```text
Download speed limit
```

Possible choices:

```text
Unlimited
1 MB/s
2 MB/s
5 MB/s
10 MB/s
Custom...
```

This is user control rather than a speed enhancement.

It is useful when the user wants to leave bandwidth available for browsing, calls, gaming, or other devices.

For parallel jobs, an overall limit is easier to understand than a separate limit per file.

---

### 6.4 Retry count

Relevant aria2c option:

```text
--max-tries
```

Friendly setting:

```text
Retry attempts
```

This is primarily a reliability control.

Higher values can help unstable connections but can also make a permanently broken download take longer to fail.

---

## 7. Important yt-dlp controls

### 7.1 HLS/DASH fragment concurrency

Relevant yt-dlp option:

```text
-N
--concurrent-fragments
```

This controls how many HLS/DASH fragments yt-dlp's native downloader fetches simultaneously.

Friendly setting:

```text
Stream fragments
```

or:

```text
Concurrent stream fragments
```

Typical conceptual values:

```text
1 — Conservative
4 — Recommended
8 — Best performance
```

These values are examples only and must be validated.

Expected effect:

- `1`: safest / least aggressive;
- higher values: more fragments downloaded concurrently;
- may significantly improve throughput on fragmented media;
- may increase server pressure;
- may not improve speed on restrictive servers.

This is especially relevant to:

- HLS;
- DASH;
- Stream Inspector workflows using yt-dlp native fragment downloading.

---

### 7.2 General retry count

Relevant yt-dlp option:

```text
--retries
```

Friendly setting:

```text
Retry attempts
```

AiDM may expose a single high-level retry setting and translate it to the appropriate engine option where practical.

The exact mapping needs to be designed carefully because yt-dlp and aria2c have different retry semantics.

---

### 7.3 Fragment retry count

Relevant yt-dlp option:

```text
--fragment-retries
```

Friendly setting:

```text
Stream fragment retries
```

This is specifically useful for fragmented HLS/DASH media.

It controls how persistent yt-dlp should be when individual fragments temporarily fail.

---

### 7.4 Bandwidth limit

Relevant yt-dlp option:

```text
--limit-rate
```

The user should ideally see one AiDM-level concept:

```text
Download speed limit
```

AiDM then applies the appropriate engine-specific option depending on which engine actually performs the transfer.

Conceptually:

```text
AiDM speed limit
├─ aria2c → --max-overall-download-limit
└─ yt-dlp native → --limit-rate
```

This abstraction is preferred over making users configure separate engine-specific speed limits.

---

## 8. Settings considered but not currently recommended

The following options are useful internally or in specialized cases, but should **not** be exposed in the first settings version unless later evidence proves a clear user need.

### yt-dlp

- `--retry-sleep`
- `--throttled-rate`
- `--http-chunk-size`
- `--buffer-size`
- `--skip-unavailable-fragments` / `--abort-on-unavailable-fragments`

These are either advanced, experimental, specialized, or difficult to explain safely to non-technical users.

### aria2c

- `--min-split-size`
- `--retry-wait`
- `--connect-timeout`
- `--timeout`
- `--lowest-speed-limit`
- `--file-allocation`
- `--disk-cache`
- `--enable-http-pipelining`

These should remain internal unless later testing and real user needs justify exposing them.

`--min-split-size` may eventually be managed automatically by profiles rather than exposed directly.

---

## 9. First-version candidate controls

Current shortlist:

1. **Connections per file**
   - aria2c `--split`
   - aria2c `--max-connection-per-server`

2. **Parallel files**
   - aria2c `--max-concurrent-downloads`

3. **Concurrent stream fragments**
   - yt-dlp `-N / --concurrent-fragments`

4. **Download speed limit**
   - aria2c `--max-overall-download-limit`
   - yt-dlp `--limit-rate`

5. **Retry attempts**
   - aria2c `--max-tries`
   - yt-dlp `--retries`

6. **Stream fragment retries**
   - yt-dlp `--fragment-retries`

7. **Restore Defaults**

8. **Persistent settings**

This shortlist is not yet final.

---

## 10. FFmpeg

FFmpeg controls are intentionally excluded from this settings concept for now.

AiDM mainly uses FFmpeg for:

- merging;
- remuxing;
- audio conversion;
- post-processing.

Exposing options such as:

- threads;
- codec;
- preset;
- compression level;

would introduce a different class of feature involving CPU usage, transcoding quality and compatibility.

That is outside the goal of these download-control settings.

If AiDM later adds explicit conversion/transcoding features, FFmpeg settings can be considered separately.

---

## 11. Persistence

User settings should survive application restarts.

The GUI already uses Qt, so `QSettings` is the preferred persistence mechanism.

Conceptually:

```text
AiDM settings
├─ profile
├─ connections_per_file
├─ parallel_files
├─ fragment_concurrency
├─ speed_limit
├─ retry_attempts
└─ fragment_retries
```

Once changed, settings remain active until the user changes them again or selects:

```text
Restore Defaults
```

The actual download process must consume the stored settings.

Settings should not merely affect UI presentation.

---

## 12. Route-aware application

Not every setting applies to every download type.

The key rule is:

```text
the engine mentioned in the route
is not necessarily
the engine transferring the bytes
```

AiDM must apply settings according to the **actual transfer engine**.

### Current GUI transfer model

#### Direct single

```text
URL
→ aria2c transfers the file
```

Relevant settings:

```text
Connections per file      applies
Speed limit               applies
Retry attempts             applies
Parallel files            not relevant
Stream fragment settings  not relevant
```

#### Direct bulk — sequential

```text
URLs
→ one aria2c transfer at a time
```

Relevant settings:

```text
Connections per file      applies
Speed limit               applies
Retry attempts             applies
Parallel files            not relevant
Stream fragment settings  not relevant
```

#### Direct bulk — parallel

```text
URLs
→ aria2c schedules and transfers multiple files
```

Relevant settings:

```text
Connections per file      applies
Parallel files            applies
Speed limit               applies
Retry attempts             applies
Stream fragment settings  not relevant
```

#### YouTube single / bulk / playlist

Current AiDM architecture is conceptually:

```text
yt-dlp
→ extracts formats / metadata / media URLs
→ aria2c performs the ordinary media transfer where supported
→ FFmpeg merges/remuxes/converts when required
```

For the current normal YouTube workflows, the performance controls that matter to the byte transfer are therefore primarily the **aria2c controls**.

Relevant settings:

```text
Connections per file      applies when aria2c is the selected transfer path
Speed limit               applies through aria2c transfer settings
Retry attempts             applies according to the actual stage/engine
Parallel files            not the same as YouTube bulk queue behavior
Stream fragment settings  normally not relevant to the ordinary aria2c handoff
```

Do not present yt-dlp fragment concurrency as a normal YouTube speed control merely because yt-dlp starts the job.

#### Browser-assisted HLS/DASH

Current Inspector stream architecture is conceptually:

```text
browser context
→ yt-dlp
→ native HLS/DASH fragment downloader
```

This is where yt-dlp native fragment controls have their clearest direct effect.

Relevant settings:

```text
Concurrent stream fragments  applies
Stream fragment retries      applies
yt-dlp speed limit           applies
aria2 split settings         do not control the native fragment transfer
Parallel files               not relevant
```

The current GUI's strongest yt-dlp-native use case is therefore the browser-assisted HLS/DASH workflow.

#### Browser-assisted non-HLS/DASH media

If the Inspector route ultimately uses yt-dlp as an extractor and delegates the actual transfer to aria2c, aria2c transfer controls apply instead.

AiDM should decide this internally from the actual command path.

### Naked HLS/DASH

Naked HLS/DASH remains a CLI capability, while its GUI execution milestone is currently deferred.

If exposed in the GUI later, the same yt-dlp-native rules should apply when yt-dlp's native HLS/DASH downloader performs the transfer.

### User-facing rule

The user should not need to understand the backend routing graph.

Each `ⓘ` explanation should explicitly say where the setting works.

For example:

```text
Connections per file

ⓘ Used for downloads handled by aria2c, including direct files
   and normal YouTube transfers. It does not change native
   HLS/DASH fragment downloading.
```

and:

```text
Concurrent stream fragments

ⓘ Used for browser-assisted HLS/DASH streams downloaded by
   yt-dlp's native fragment downloader. It does not affect
   direct files or normal YouTube transfers handled by aria2c.
```

AiDM should apply only the settings relevant to the engine/path actually doing the transfer.

---

## 13. Safety principles

The settings system must follow these rules:

1. **Higher numbers are not automatically treated as better.**
2. **AiDM should ship with safe defaults.**
3. **One clearly marked recommendation should exist for uncertain users.**
4. **A performance-oriented option may be marked separately from the default.**
5. **Aggressive combinations must be constrained or warned about.**
6. **Settings should map to proven backend flags only.**
7. **No experimental engine flag should be exposed casually.**
8. **Settings must never silently break existing CLI defaults unless deliberately integrated later.**
9. **GUI labels should describe user concepts, not command-line syntax.**
10. **Restore Defaults must always provide an easy escape path.**

---

## 14. Open questions for the next discussion

Before implementation, decide:

1. Exact profile names.
2. Exact default profile.
3. Exact numeric values for Conservative / Balanced / Fast.
4. Which values deserve the labels `Recommended` and `Best performance` for the remaining controls. (`Connections per file` is already locked.)
5. Safe maximum for:
   - parallel files;
   - fragment concurrency. (`Connections per file` is locked at 8.)
6. Whether settings should expose presets only or presets + Custom mode.
7. Whether changing a single control automatically switches the profile to Custom.
8. Whether high combined connection counts should show a warning.
9. Exact tooltip text for every setting.
10. How one high-level retry setting should map across aria2c and yt-dlp.
11. Whether bandwidth limit should be global across all engines or configured per engine internally.
12. Whether the settings surface should be a popover, dialog, stacked page or separate window.
13. Whether advanced engine names/flags should appear anywhere in the UI.
14. Whether these settings should initially affect GUI downloads only or be shared with the CLI later.

---

## 15. Current design direction

The current preferred direction is:

```text
⚙ Settings
   ↓
simple user-facing controls
   ↓
recommended choices clearly marked
   ↓
persistent QSettings
   ↓
route-aware translation
   ↓
yt-dlp / aria2c flags
```

The intended experience is:

```text
user wants more control
        ↓
opens Settings
        ↓
reads simple explanation
        ↓
sees Recommended / Best performance guidance
        ↓
chooses safely
        ↓
AiDM handles engine complexity
```

This document should continue evolving through discussion and testing before any implementation begins.
