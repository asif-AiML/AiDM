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

## 2. Settings UI — LOCKED DESIGN

The settings UI should remain simple, minimal and visually secondary to the main downloader.

AiDM will use a **right-side settings drawer** rather than replacing or suppressing the main download surface.

### Entry control

Place a compact three-horizontal-bars control in the top-right area of the main AiDM box:

```text
AiDM                                      ☰
```

The hamburger/sidebar symbol is preferred over a three-dots menu because the action opens a panel rather than a generic list of actions.

### Opening behavior

When the user activates the control:

1. a settings drawer slides in from the right;
2. the main AiDM surface remains visible;
3. the main surface receives a translucent dim overlay;
4. the main surface becomes temporarily non-interactive while the drawer has focus.

Use a dim overlay rather than a real-time blur effect.

Reason:

- it provides the same visual focus shift;
- it is simpler and more reliable in PySide6;
- it avoids inconsistent or expensive blur behavior across Linux desktop environments.

Conceptually:

```text
┌──────────────────────────────────────────────┐
│ dimmed AiDM surface     │ Download Settings │
│                         │                   │
│                         │ Profile           │
│                         │ [ Balanced ▼ ]   │
│                         │                   │
│                         │ PERFORMANCE       │
│                         │ Connections/file │
│                         │ [ 4 ▼ ]       ⓘ │
│                         │                   │
│                         │ Parallel files   │
│                         │ [ 4 ▼ ]       ⓘ │
│                         │                   │
│                         │ Stream fragments │
│                         │ [ 4 ▼ ]       ⓘ │
│                         │                   │
│                         │ BANDWIDTH         │
│                         │ Speed limit      │
│                         │ [ Unlimited ▼ ]ⓘ│
│                         │                   │
│                         │ RELIABILITY       │
│                         │ Retry attempts   │
│                         │ [ Auto ▼ ]    ⓘ │
│                         │ Fragment retries │
│                         │ [ Auto ▼ ]    ⓘ │
│                         │                   │
│                         │ [Restore Defaults]│
└──────────────────────────────────────────────┘
```

### Control order

The drawer should present controls in this order:

```text
Performance profile

PERFORMANCE
Connections per file
Parallel files
Concurrent stream fragments

BANDWIDTH
Download speed limit

RELIABILITY
Retry attempts
Stream fragment retries

Restore Defaults
```

Profiles sit at the top because they provide the quickest high-level performance choice.

### No Save button

There is intentionally **no Save button**.

Every setting change is persisted immediately through `QSettings`.

Conceptually:

```text
user changes setting
→ update in-memory settings state
→ persist to QSettings immediately
→ show lightweight confirmation
```

This avoids hidden unsaved state and ensures changes are not lost if the application closes unexpectedly after editing settings.

### Saved notification

After a setting change is persisted, AiDM should show a small non-blocking in-app confirmation such as:

```text
Settings saved
```

or:

```text
Settings saved successfully
```

This should behave like a lightweight toast/status notification.

It must **not** be a modal dialog requiring an OK click.

Repeated rapid changes may reuse/refresh the same notification rather than stacking multiple popups.

### Closing behavior

The drawer closes when the user:

```text
clicks ☰ again
OR
clicks the dimmed main AiDM area
```

Closing reverses the animation and restores the normal main UI interaction state.

Closing the drawer does not perform a separate save operation because values are already persisted.

### Animation

Keep animation restrained and functional:

```text
open  → drawer slides in from the right
close → drawer slides back to the right
duration ≈ 180–250 ms
```

The dim overlay may fade in/out alongside the drawer.

Do not add bouncing, scaling or decorative animation.

### Active-download rule

Opening Settings during an active download must not alter the command of the process already running.

Any changed setting applies to the **next download job**.

Conceptually:

```text
download A already running
→ user changes Fast → Balanced
→ download A continues unchanged
→ download B uses Balanced settings
```

This keeps process behavior deterministic and avoids trying to mutate active aria2c or yt-dlp command lines.

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

## 5. Performance profiles — LOCKED DESIGN

Profiles are **preset bundles of already-defined controls**.

They do not introduce new backend behavior.

Profiles apply only to the three performance/concurrency controls:

```text
Connections per file
Parallel files
Concurrent stream fragments
```

The following settings remain independent and are **not changed by a performance profile**:

```text
Download speed limit
Retry attempts
Stream fragment retries
```

This prevents a user from accidentally losing a bandwidth cap or reliability preference simply because they switched performance profile.

### Locked profiles

```text
Conservative
Balanced
Fast
Custom
```

#### Conservative

```text
Connections per file        = 1
Parallel files              = 2
Concurrent stream fragments = 1
```

Intent:

- lowest concurrency;
- maximum compatibility;
- least aggressive network/server behavior.

#### Balanced

```text
Connections per file        = 4
Parallel files              = 4
Concurrent stream fragments = 4
```

Intent:

- moderate concurrency;
- strong general-purpose performance;
- safe middle ground.

#### Fast

```text
Connections per file        = 8
Parallel files              = 4
Concurrent stream fragments = 8
```

Intent:

- strongest performance-oriented preset exposed by AiDM;
- keeps Parallel files capped at 4;
- respects the first-version accepted aria2 ceiling:

```text
4 parallel files × 8 connections per file
≈ up to 32 simultaneous aria2 connections
```

This profile does not imply guaranteed maximum speed on every server.

#### Custom

Custom means the user has manually selected one or more of the three performance controls.

Example:

```text
Balanced selected
→ 4 / 4 / 4

user changes Connections per file to 8
→ profile becomes Custom
```

If the user later selects Balanced again:

```text
→ restore 4 / 4 / 4
```

### Auto and profiles

The individual Connections per file control includes:

```text
Auto — Recommended
```

Auto remains a valid individual setting.

However, profiles intentionally use explicit numeric values rather than Auto.

Reason:

```text
Auto
→ preserve AiDM's route-specific proven defaults

Profile
→ deliberately apply a known performance preset
```

These are different concepts and should remain separate.

### Profile interaction rule

Selecting a profile should immediately set the three performance controls to that profile's locked values.

Changing any one of those three controls manually should switch the profile indicator to:

```text
Custom
```

Changing:

```text
Download speed limit
Retry attempts
Stream fragment retries
```

must **not** switch the performance profile to Custom because those controls are outside the profile bundle.

### Persistence

The selected profile and the underlying control values should persist through QSettings.

Conceptually:

```text
performance_profile
connections_per_file
parallel_files
fragment_concurrency
```

The persisted values must remain internally consistent.

### First-version profile table

| Profile | Connections per file | Parallel files | Concurrent stream fragments |
|---|---:|---:|---:|
| Conservative | 1 | 2 | 1 |
| Balanced | 4 | 4 | 4 |
| Fast | 8 | 4 | 8 |
| Custom | user-selected | user-selected | user-selected |

### Information text

The first-version profile `ⓘ` explanation should communicate:

```text
Download profile

Quickly applies a preset to AiDM's performance controls.

Conservative uses the lowest concurrency for maximum
compatibility.

Balanced uses moderate concurrency for general use.

Fast uses AiDM's strongest first-version performance settings.

Custom appears when you manually change one of the performance
controls.

Profiles do not change your speed limit or retry settings.
```

The wording may be polished during final GUI implementation, but the meaning above is locked.

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

### 6.2 Parallel files — LOCKED DESIGN

Relevant aria2c option:

```text
--max-concurrent-downloads
```

This control applies only to:

```text
Direct bulk → Parallel
```

Friendly control:

```text
Parallel files
```

#### Locked choices

The first version should expose:

```text
2 — Conservative
4 — Recommended
```

The default/recommended value is:

```text
4
```

No higher values are needed in the first version.

The goal is a simple queue model rather than exposing every possible aria2 concurrency value.

#### Queue behavior

Example:

```text
10 files total
4 active
2 complete
4 waiting
```

Displayed compactly in the GUI as:

```text
10 files • 4 active • 2 complete • 4 waiting
```

When one active file completes:

```text
one waiting file starts
→ active count returns to 4
```

until the queue is exhausted.

#### Backend mapping

If the user selects:

```text
Parallel files = 4
```

AiDM should apply:

```text
--max-concurrent-downloads=4
```

If the user selects:

```text
Parallel files = 2
```

AiDM should apply:

```text
--max-concurrent-downloads=2
```

#### Interaction with Connections per file

These two controls operate at different levels and are not contradictory:

```text
Parallel files
→ number of separate files active at once

Connections per file
→ number of connections one active file may use
```

Example:

```text
Parallel files = 4
Connections per file = 4

→ 4 active files
→ up to 4 connections per file
→ up to about 16 simultaneous connections
```

With the first-version maximum Connections per file value:

```text
Parallel files = 4
Connections per file = 8

→ up to about 32 simultaneous connections
```

This is the accepted first-version ceiling.

No extra warning system or dynamic conflict resolution is required beyond keeping Parallel files capped at 4 and Connections per file capped at 8.

#### Applicability

Applies to:

```text
Direct bulk → Parallel    yes
```

Does not apply to:

```text
Direct single             no
Direct bulk → Sequential  no
YouTube single            no
YouTube bulk              no
YouTube playlist          no
HLS/DASH                  no
```

#### Locked information text

The first-version `ⓘ` explanation should communicate:

```text
Parallel files

Controls how many files download at the same time in Direct Bulk
→ Parallel mode.

With 4 selected, up to 4 files download while the rest wait.
When one finishes, the next waiting file starts.

This works together with Connections per file. For example,
4 parallel files with 4 connections each can use up to about
16 connections.

This setting affects only Direct Bulk → Parallel downloads.
```

The wording may be polished during final GUI implementation, but the meaning above is locked.

#### Testing requirement

No long performance benchmark is required.

A short behavior test with several small direct URLs is enough.

Suggested implementation-phase checks:

```text
Parallel files = 2
→ verify 2 active and the remainder waiting

Parallel files = 4
→ verify 4 active and the remainder waiting
```

Also verify that when one active file completes, the next waiting file starts automatically.

The purpose is to validate queue behavior and command wiring, not to benchmark total throughput.

---

### 6.3 Download speed limit — LOCKED DESIGN

Primary aria2c option:

```text
--max-overall-download-limit
```

Friendly control:

```text
Download speed limit
```

aria2c is the primary target for this setting because it performs the actual transfer for most current AiDM download paths, including direct downloads and normal YouTube transfers delegated by yt-dlp.

#### Locked choices

The first version should expose:

```text
Unlimited — Recommended
1 MB/s
2 MB/s
5 MB/s
10 MB/s
```

There is intentionally **no Custom option**.

The user does not need arbitrary bandwidth values, and removing Custom avoids confusing or unrealistic entries such as extremely high manual limits.

#### Unlimited — Recommended

Meaning:

```text
no artificial AiDM bandwidth cap
```

AiDM allows the active transfer engine to use as much bandwidth as the server, network and connection conditions permit.

This is the recommended/default choice.

#### Limited values

```text
1 MB/s
2 MB/s
5 MB/s
10 MB/s
```

These values intentionally trade maximum download speed for available bandwidth.

They are useful when the user wants to leave bandwidth available for:

- browsing;
- calls;
- gaming;
- other devices;
- other network activity.

#### aria2c mapping

For aria2c-backed downloads:

```text
Unlimited
→ do not apply an artificial overall speed limit

1 MB/s
→ --max-overall-download-limit=1M

2 MB/s
→ --max-overall-download-limit=2M

5 MB/s
→ --max-overall-download-limit=5M

10 MB/s
→ --max-overall-download-limit=10M
```

This is especially useful for Direct Bulk → Parallel because the limit applies to the aria2c process as a whole rather than separately multiplying a per-file cap across every active item.

#### yt-dlp native mapping

For browser-assisted HLS/DASH where yt-dlp's native downloader actually transfers the media:

```text
Unlimited
→ no artificial yt-dlp rate limit

1 MB/s
→ --limit-rate 1M

2 MB/s
→ --limit-rate 2M

5 MB/s
→ --limit-rate 5M

10 MB/s
→ --limit-rate 10M
```

This keeps one user-facing AiDM control while applying the correct engine-specific flag.

#### Applicability

Primary current applicability:

```text
Direct single                         yes, via aria2c
Direct bulk sequential                yes, via aria2c
Direct bulk parallel                  yes, via aria2c
Normal YouTube transfer via aria2c    yes, via aria2c
Other aria2c-backed media transfers   yes
Browser-assisted HLS/DASH             yes, via yt-dlp native
```

The practical emphasis remains aria2c because it handles the large majority of actual transfer work in current AiDM routes.

yt-dlp-native rate limiting mainly matters for browser-assisted HLS/DASH streams.

#### Locked information text

The first-version `ⓘ` explanation should communicate:

```text
Download speed limit

Limits how much download bandwidth AiDM may use. Lower values
leave more bandwidth available for browsing, calls, gaming or
other devices.

Unlimited — Recommended removes the artificial cap and lets
AiDM use as much speed as the server and network allow.

This setting mainly affects downloads handled by aria2c,
including direct files and normal YouTube transfers. For
browser-assisted HLS/DASH streams, AiDM applies the equivalent
limit to yt-dlp's native downloader.
```

The wording may be polished during final GUI implementation, but the meaning above is locked.

#### Testing requirement

No long performance benchmark is required.

A short wiring test is sufficient.

Suggested implementation-phase checks:

```text
2 MB/s
→ verify transfer speed is constrained around the configured cap

Unlimited
→ verify the artificial cap is removed
```

Test at least one aria2c-backed transfer.

A short browser-assisted HLS/DASH check should also verify that the equivalent yt-dlp rate limit is passed correctly.

Full download completion is not required solely for validating this setting.

---

### 6.4 Retry attempts — LOCKED DESIGN

Primary aria2c option:

```text
--max-tries
```

Friendly control:

```text
Retry attempts
```

aria2c is the primary target for this setting because it performs most current AiDM transfers.

For browser-assisted HLS/DASH, AiDM applies the equivalent general retry setting to yt-dlp.

#### Locked choices

The first version should expose:

```text
Auto — Recommended
3 — Quick failure
5 — Balanced
10 — Persistent
```

#### Auto — Recommended

`Auto` preserves the normal retry behavior of whichever engine is actually transferring the data.

Conceptually:

```text
aria2c-backed downloads
→ keep aria2c's normal retry behavior

browser-assisted HLS/DASH via yt-dlp
→ keep yt-dlp's normal retry behavior
```

This avoids silently changing established retry behavior for users who never modify the setting.

#### 3 — Quick failure

Use fewer retries.

Useful when the user prefers a broken download to fail sooner rather than waiting through many repeated attempts.

#### 5 — Balanced

A moderate retry policy.

Useful for ordinary unstable connections without making failures excessively slow to surface.

#### 10 — Persistent

A more patient retry policy.

Useful when:

- the connection is weak;
- the server is temporarily unreliable;
- occasional failures are expected.

A permanently broken download may take longer to give up.

#### Engine mapping

When the user selects an explicit numeric value:

```text
aria2c
→ --max-tries=N

yt-dlp native HLS/DASH
→ --retries N
```

The GUI exposes one AiDM concept while the backend applies the corresponding flag to the actual transfer engine.

#### Applicability

```text
Direct single                         yes, via aria2c
Direct bulk sequential                yes, via aria2c
Direct bulk parallel                  yes, via aria2c
Normal YouTube transfer via aria2c    yes, via aria2c
Other aria2c-backed media             yes

Browser-assisted HLS/DASH             yes, via yt-dlp --retries
```

#### Important distinction

This setting controls **general download/connection retry attempts**.

It is separate from:

```text
Stream fragment retries
→ yt-dlp --fragment-retries
```

HLS/DASH fragment retry behavior is a separate control because retrying one failed media fragment is different from retrying the broader download/request stage.

#### Locked information text

The first-version `ⓘ` explanation should communicate:

```text
Retry attempts

Controls how many times AiDM retries after a temporary download
or connection failure. More retries can help unstable networks,
but a permanently broken download will take longer to give up.

Auto — Recommended keeps the normal retry behavior of the active
download engine. 3 gives up sooner, 5 is balanced, and 10 is
more persistent.

For most downloads this controls aria2c. For browser-assisted
HLS/DASH streams, AiDM applies the equivalent retry setting to
yt-dlp.
```

The wording may be polished during final GUI implementation, but the meaning above is locked.

#### Testing requirement

No long failure simulation is required.

Implementation-phase checks only need to verify that:

- Auto leaves explicit retry flags unset;
- numeric choices map to the correct engine flag;
- aria2c receives `--max-tries=N`;
- browser-assisted HLS/DASH receives yt-dlp `--retries N`.

A deliberately flaky network test is optional rather than required for first implementation.

---

## 7. Important yt-dlp controls

### 7.1 Concurrent stream fragments — LOCKED DESIGN

Relevant yt-dlp option:

```text
-N
--concurrent-fragments
```

Friendly control:

```text
Concurrent stream fragments
```

This control applies when yt-dlp's **native HLS/DASH fragment downloader** is actually transferring the media.

For the current GUI architecture, the main use case is:

```text
Browser-assisted HLS/DASH
→ yt-dlp native downloader
```

#### Locked choices

The first version should expose:

```text
1 — Maximum compatibility
4 — Recommended
8 — Best performance
```

The default/recommended value is:

```text
4
```

No Auto option is needed for this control.

Unlike aria2-backed routes, there is no need to preserve different route-specific connection defaults here. The setting exists specifically to control yt-dlp native fragment concurrency.

#### 1 — Maximum compatibility

Meaning:

```text
one HLS/DASH fragment downloaded at a time
```

Expected behavior:

- least aggressive;
- safest with restrictive servers;
- useful if higher concurrency causes errors;
- may be slower on servers that support parallel fragment fetching.

#### 4 — Recommended

Meaning:

```text
up to four HLS/DASH fragments downloaded concurrently
```

Expected behavior:

- balanced concurrency;
- recommended general-purpose choice;
- can improve stream download throughput without using the strongest exposed setting.

#### 8 — Best performance

Meaning:

```text
up to eight HLS/DASH fragments downloaded concurrently
```

Expected behavior:

- strongest performance-oriented value exposed in the first version;
- may provide higher throughput on servers that benefit from fragment concurrency;
- is not guaranteed to be faster on every server;
- some servers may restrict or throttle higher concurrency.

The label `Best performance` means the strongest performance-oriented choice intentionally exposed by AiDM, not a universal speed guarantee.

#### Applicability

Applies to:

```text
Browser-assisted HLS/DASH using yt-dlp native fragments    yes
Future naked HLS/DASH GUI path using yt-dlp native         yes
```

Does not apply to:

```text
Direct single                                               no
Direct bulk sequential                                      no
Direct bulk parallel                                        no
Normal YouTube transfer delegated to aria2c                 no
Other aria2c-backed media transfers                         no
```

The fact that yt-dlp participates in a route does not make this setting relevant unless yt-dlp's native fragment downloader is the component transferring the media.

#### Locked information text

The first-version `ⓘ` explanation should communicate:

```text
Concurrent stream fragments

Controls how many pieces of an HLS/DASH stream yt-dlp
downloads at the same time. Higher values can improve stream
download speed, but some servers may not benefit from extra
concurrency.

1 offers maximum compatibility, 4 is recommended, and 8 is
the performance-oriented choice.

This setting affects browser-assisted HLS/DASH downloads
handled by yt-dlp's native fragment downloader. It does not
affect direct downloads or normal YouTube transfers handled
by aria2c.
```

The wording may be polished during final GUI implementation, but the meaning above is locked.

#### Testing requirement

No long download session is required.

A short browser-assisted HLS/DASH test is enough.

Suggested implementation-phase checks:

```text
-N 1 → run briefly
-N 4 → run briefly
-N 8 → run briefly
```

About 20–30 seconds per run is sufficient.

The purpose is to verify:

- the selected value is correctly passed to yt-dlp;
- fragment concurrency remains operational;
- no obvious failure appears;
- 4 and 8 remain sane choices.

Full stream completion is not required solely for validating this setting.

---

### 7.2 General retry count

yt-dlp native uses:

```text
--retries
```

The user does **not** receive a separate yt-dlp general-retry control.

The single locked AiDM control is defined in:

```text
6.4 Retry attempts — LOCKED DESIGN
```

AiDM applies that setting according to the actual transfer engine:

```text
aria2c-backed transfer
→ --max-tries

yt-dlp-native browser-assisted HLS/DASH
→ --retries
```

This remains separate from yt-dlp `--fragment-retries`, which is handled by the dedicated Stream fragment retries control.

---

### 7.3 Stream fragment retries — LOCKED DESIGN

Relevant yt-dlp option:

```text
--fragment-retries
```

Friendly control:

```text
Stream fragment retries
```

This setting applies specifically to HLS/DASH media downloaded by yt-dlp's native fragment downloader.

Its purpose is reliability: if an individual media fragment fails temporarily, yt-dlp can retry that fragment instead of giving up immediately.

This is especially useful on weak or unstable networks.

#### Locked choices

The first version should expose:

```text
Auto — Recommended
5 — Balanced
10 — Persistent
20 — Very persistent
```

#### Auto — Recommended

Auto preserves yt-dlp's normal fragment retry behavior.

AiDM should not add an explicit `--fragment-retries` value when Auto is selected.

This keeps the engine's proven default behavior unless the user explicitly asks for a more persistent policy.

#### 5 — Balanced

A moderate manual retry policy.

Useful when the user wants some added resilience without making permanently unavailable fragments wait too long.

#### 10 — Persistent

A stronger retry policy.

Useful for:

- unstable Wi-Fi;
- weak mobile connections;
- temporary packet loss;
- streaming servers that occasionally fail individual fragment requests.

#### 20 — Very persistent

The strongest fragment-retry value exposed in the first version.

Useful when successful completion matters more than failing quickly.

Trade-off:

A permanently unavailable fragment can take considerably longer to give up.

#### Backend mapping

When the user selects an explicit numeric value:

```text
5
→ --fragment-retries 5

10
→ --fragment-retries 10

20
→ --fragment-retries 20
```

When Auto is selected:

```text
do not add an explicit --fragment-retries override
```

#### Applicability

Applies to:

```text
Browser-assisted HLS/DASH using yt-dlp native fragments    yes
Future naked HLS/DASH GUI path using yt-dlp native         yes
```

Does not apply to:

```text
Direct single                                               no
Direct bulk sequential                                      no
Direct bulk parallel                                        no
Normal YouTube transfers delegated to aria2c                no
Other aria2c-backed transfers                               no
```

#### Relationship to Retry attempts

This control is separate from the general Retry attempts setting.

```text
Retry attempts
→ broader download / connection retry policy

Stream fragment retries
→ retry one failed HLS/DASH media fragment
```

Example:

```text
fragment 527 fails
→ retry fragment 527
→ if it succeeds, continue downloading the stream
```

This separation gives users more resilience without confusing general network retries with per-fragment recovery.

#### Locked information text

The first-version `ⓘ` explanation should communicate:

```text
Stream fragment retries

Controls how many times AiDM retries an individual HLS/DASH
fragment when it fails.

Higher values can improve the chance of completing long streams
on weak or unstable connections, but a permanently unavailable
fragment will take longer to give up.

Auto — Recommended keeps yt-dlp's normal fragment retry
behavior. 5 is balanced, 10 is persistent, and 20 is very
persistent.

This setting affects only browser-assisted HLS/DASH downloads
handled by yt-dlp's native fragment downloader.
```

The wording may be polished during final GUI implementation, but the meaning above is locked.

#### Testing requirement

No long unstable-network test is required.

Implementation-phase checks only need to verify:

```text
Auto
→ no explicit --fragment-retries override

5
→ --fragment-retries 5

10
→ --fragment-retries 10

20
→ --fragment-retries 20
```

A real weak-network HLS/DASH test is useful later, but not required to validate the first implementation.

---

### 7.4 Bandwidth limit

yt-dlp native uses:

```text
--limit-rate
```

The user does **not** receive a separate yt-dlp speed-limit control.

The single locked AiDM control is defined in:

```text
6.3 Download speed limit — LOCKED DESIGN
```

AiDM applies that setting to the actual transfer engine:

```text
aria2c-backed transfer
→ --max-overall-download-limit

yt-dlp-native HLS/DASH transfer
→ --limit-rate
```

aria2c remains the primary practical target because it performs most current AiDM transfers.

yt-dlp-native rate limiting is mainly relevant to browser-assisted HLS/DASH.

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

## 11. Persistence — LOCKED DESIGN

User settings must survive application restarts.

AiDM will use Qt `QSettings`.

Conceptually:

```text
AiDM settings
├─ performance_profile
├─ connections_per_file
├─ parallel_files
├─ fragment_concurrency
├─ speed_limit
├─ retry_attempts
└─ fragment_retries
```

Each change is persisted immediately.

There is no separate Save step.

The active settings remain in effect until the user changes them or activates:

```text
Restore Defaults
```

Restore Defaults should ask for a small confirmation before replacing several stored values at once.

After persistence succeeds, the GUI may show the locked lightweight in-app notification:

```text
Settings saved
```

The actual download command builders must consume the stored values.

Settings must never be cosmetic UI-only state.

Changes made while a download is already running apply only to future jobs.

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

## 14. Remaining implementation decisions

The control contracts, performance profiles and settings drawer UI are now locked.

Remaining decisions are implementation-level rather than UI-model questions.

Before coding is considered complete, confirm:

1. the exact initial/default persisted state for a brand-new installation, especially how the profile indicator represents AiDM's existing route-specific `Connections per file = Auto` behavior;
2. whether these settings are initially GUI-only or later shared with the CLI;
3. the exact PySide6 widget choices and internal settings-state abstraction;
4. final wording polish for labels and information popovers without changing their locked meaning;
5. the final Restore Defaults baseline once the new-install default state is locked.

---
## 15. Locked design direction

The settings experience is now:

```text
☰
↓
right-side settings drawer
↓
Performance profile at top
↓
simple grouped controls
↓
Recommended / compatibility / performance guidance
↓
immediate QSettings persistence
↓
non-blocking "Settings saved" confirmation
↓
route-aware translation
↓
aria2c / yt-dlp flags
```

The intended user experience is:

```text
user wants more control
        ↓
opens the side drawer
        ↓
main AiDM surface stays visible but dimmed
        ↓
chooses a profile or individual setting
        ↓
AiDM persists the value immediately
        ↓
small saved confirmation appears
        ↓
user closes drawer by ☰ or dimmed area
        ↓
next download job consumes the new settings
```

The first-version settings design is intentionally constrained:

- no raw engine flags;
- no Custom bandwidth value;
- no excessive concurrency values;
- no Save button;
- no live mutation of an already-running download;
- no real-time blur requirement;
- no FFmpeg performance controls.

Implementation should preserve these locked behaviors unless a later design change is explicitly discussed and documented.
