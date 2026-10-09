# AiDM Advanced Download Controls — Design Notes

> **Status:** Draft / discussion document  
> **Branch:** `feat/gui`  
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

### 6.1 Connections per file

Relevant aria2c options:

```text
--split
--max-connection-per-server
```

These options are closely related.

Exposing them separately to a non-technical user would create confusion, so AiDM should likely expose one friendly setting:

```text
Connections per file
```

AiDM can translate the selected value into an appropriate combination of:

```text
--split=N
--max-connection-per-server=N
```

Expected effect:

- `1`: one connection, most conservative;
- higher values: multiple pieces of the same file can download simultaneously;
- may improve large-file throughput;
- may provide no benefit on already-fast or connection-limited servers;
- very high values may cause server throttling or connection rejection.

This is a strong candidate for the first version.

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

Examples:

### Direct file

```text
Connections per file      applies
Parallel files            not relevant to single file
Stream fragment settings  not relevant
Speed limit               applies
Retries                   applies
```

### Direct bulk parallel

```text
Connections per file      applies
Parallel files            applies
Speed limit               applies
Retries                   applies
```

### HLS/DASH native yt-dlp

```text
Stream fragment concurrency applies
Fragment retries             applies
yt-dlp speed limit           applies
aria2 split settings         not relevant
```

### YouTube

Behavior depends on whether yt-dlp delegates the actual transfer to aria2c or uses a native fragmented downloader.

AiDM should apply only the settings relevant to the engine/path actually being used.

The user should not need to understand this distinction.

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
4. Which values deserve the labels:
   - Recommended
   - Best performance
5. Safe maximum for:
   - connections per file;
   - parallel files;
   - fragment concurrency.
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
