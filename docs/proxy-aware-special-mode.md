# Proxy-aware special mode — AiDM design decision

**Status:** implemented; offline validation complete. Live integrated proxy/download checks remain manual.
**Branch:** `feat/controls-settings`. **Scope:** AiDM only.

## Motivation and evidence

A user tested the independent `yt-dlp` command below while the **standalone Psiphon-Linux** tunnel was running:

```bash
yt-dlp --proxy "socks5h://127.0.0.1:1081" "URL"
```

With a URL from a website normally blocked by the ISP, the download **started and completed**. This establishes that this yt-dlp + Psiphon SOCKS5 route works for the tested URL/session, not that every site or media type will work or that AiDM integration has already passed.

**Decision:** Do **not** embed or bundle the Psiphon engine in AiDM. Instead add an **occasional, opt-in, provider-neutral SOCKS5 special mode**, usable with an independently running Psiphon-Linux instance or another compatible proxy (e.g. Tor). Normal AiDM must not depend on either provider.

## GUI specification

Place an optional **Proxy-aware special mode** section in AiDM's existing settings UI (see `download-controls-settings-plan.md`).

- Two input fields: **SOCKS host** and **SOCKS port**, empty on a fresh installation.
  `(e.g. 127.0.0.1 : 1081)` is muted helper text only, never a default or implicit fallback.
- **Save** stores validated host/port persistently for future launches. This explicit Save action is a **special-mode exception** to the current automatic-save rule for ordinary download controls; do not silently alter those controls.
- Independent **ON/OFF** checkbox; **OFF on every launch**, with enablement never persisted.
  ON never launches an external provider or modifies Linux system/browser proxy settings.
- Only the last successfully saved endpoint is authoritative. Unsaved edits are not used when
  enabling the mode. Enabling without a saved valid endpoint is refused with local feedback.
  Invalid saves preserve the previous endpoint and do not show the save toast.
- Saved host/port remain available while OFF and across restarts. Restore Defaults concerns
  only the ordinary download controls and never clears the endpoint.
- A calm, centered main-window indicator and **Turn Off** button appear only while enabled,
  occupying no space while hidden. The button and drawer checkbox update the same runtime state.
- All feature labels, notices, validation messages, help, and errors are provider-neutral.
- Validate nonempty host, integer port 1–65535, and safe URL construction. Prefer `socks5h://host:port` for proxy-side hostname resolution. Pass arguments as an argument array, never string interpolation into a shell.
- Display a concise notice: *Special mode supports one download at a time; most advanced AiDM features are unavailable.*
- If the proxy is unreachable or download fails, **do not fall back to direct download** while this mode is ON; report a clear error.

## Routing contract

| Input or feature | Proxy OFF | Proxy ON (special mode) |
| --- | --- | --- |
| One direct HTTP/HTTPS file link | Existing aria2c path | **yt-dlp** + `--proxy`; no aria2c delegation |
| One supported media-page URL | Existing yt-dlp workflow | **yt-dlp** + `--proxy` |
| One standalone HLS/DASH URL | Existing stream route | **yt-dlp** + `--proxy` where supported |
| One Stream Inspector handoff from a blocked site | Existing media/context handling | **yt-dlp** + `--proxy`, preserving necessary captured browser request context |
| Playlists and bulk URL lists | Existing capabilities | **Disabled / reject** |
| Sequential or parallel batch controls | Existing capabilities | **Disabled** |
| Separate subtitle download workflow | Existing capabilities | **Disabled** |
| Torrent and magnet handling | Existing capabilities | **Disabled** |
| aria2c-accelerated direct downloading | Existing capabilities | **Not used** |
| Other download controls | Existing behavior | Profile, six ordinary controls, and Restore Defaults disabled; stored values untouched |

The user intentionally calls this an **occasional special weapon**, not a parallel implementation of the complete downloader. Do **not** build new playlist, bulk, HLS/DASH parsing, subtitle, concurrency or parallel-control architectures solely for this mode. Existing yt-dlp stream extraction can be reused; one supported stream can still be downloaded. Explicitly suppress playlist traversal (e.g. appropriate yt-dlp `--no-playlist` behavior) and reject unsupported multi-URL inputs before launching.

Browser-captured context (e.g. Referer and User-Agent, where available) should be passed to yt-dlp as it is in the existing handoff. A proxied request is not a substitute for valid tokens, cookies, referer or permitted access.

## Implemented execution and state boundaries

- `ProxySettings` owns the saved validated endpoint and runtime enablement separately from
  `DownloadSettings`. It stores the host/port pair in `proxy/endpoint`; no enablement key is written.
- A frozen `ProxyEndpoint` in `DownloadJob.proxy` records special mode and its endpoint;
  `None` records normal mode. Changing mode or saving another endpoint never rebuilds or
  restarts an active process. Retry uses the original job and endpoint, even after mode is OFF.
  A newly configured job uses current runtime state and the last saved endpoint.
- Special-mode classification is local only: no direct GET/HEAD probes, metadata requests,
  or quality discovery. Existing normal-mode inspection results are invalidated on mode changes.
  An already-started normal-mode probe may finish, but its stale result is ignored.
- A single yt-dlp adapter handles direct URLs, media pages (including single YouTube URLs),
  standalone HLS/DASH, and Inspector media. Special mode uses automatic format selection;
  normal YouTube audio/quality options and performance settings are not applied. Normal-mode
  standalone-stream execution remains unchanged/deferred.
- Inspector title, exact media URL, User-Agent, and Referer are preserved. Attached subtitle
  URLs are not executed; standalone subtitle input is rejected. No aria2 stage is started.
- Commands pass `--proxy socks5h://HOST:PORT` as list arguments, use native transfers,
  ignore external yt-dlp configuration/plugins, and suppress playlists. Known playlist inputs
  are rejected locally; `--break-match-filters !playlist` rejects extracted playlist entries
  and `--playlist-items 1` bounds traversal. Bulk/torrent/magnet inputs are rejected locally.
- Only HTTP/native HLS/DASH formats are selected. Some HLS streams require yt-dlp's internal
  FFmpeg download fallback, which cannot use SOCKS. Special mode denies network protocols in
  FFmpeg downloader input arguments, making those streams fail rather than connect directly.
  Local FFmpeg merging/post-processing remains available. No automatic direct retry exists.
- Ordinary controls retain their exact values and become available again when mode is OFF.
  The CLI and all normal-mode command builders remain independent of saved proxy settings.

Offline tests cover endpoint validation/persistence, restart-OFF behavior, unsaved edits,
shared UI state, keyboard/scroll/help interactions, command routing, no sidecar/fallback,
active/retry snapshots, and normal-mode regressions. Installed yt-dlp option/format parsing
is also checked locally. This does not replace live endpoint/site compatibility testing.

Validation on 2026-10-23: **354 tests passed**, including 18 new proxy tests, using
`QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v`.
Syntax and `git diff --check` checks passed. Offscreen screenshots confirmed layout at
small window sizes; desktop theme and live network behavior were not tested.

## Safety and acceptance tests

1. OFF: all original AiDM routing and features remain unchanged.
2. Save a valid SOCKS host/port, relaunch AiDM, and verify they persist without turning the feature on unexpectedly.
3. ON with active external Psiphon: verify a **single** direct file routes to yt-dlp, not aria2c, with the SOCKS proxy argument.
4. ON with a supported website and one Stream Inspector HLS/DASH handoff: verify yt-dlp receives proxy and available captured headers; confirm actual completion on test content.
5. ON with unavailable proxy: fail clearly, without direct ISP fallback.
6. ON with playlist, bulk, separate subtitles, torrent/magnet: unsupported operations are clearly disabled/rejected.
7. OFF after testing: original workflows still pass.
8. Test another SOCKS5 provider separately before claiming it works; the design is generic but Psiphon is the only verified provider in the present experiment.

## Boundaries

- AiDM never starts/stops the Psiphon-Linux process in this design.
- No Psiphon binary, datastore, GUI, or source duplication inside AiDM.
- Stream Inspector remains an independent capture tool; it does not itself perform downloads.
- Firefox proxy switching belongs to Stream Inspector's optional Firefox-specific integration with the **standalone** Psiphon controller, not to this AiDM setting.
- The prior successful manual yt-dlp test is **evidence** for that session; the final
  integrated feature still needs the manual checks below before live compatibility is claimed.

## Manual integrated check

1. Start an independently configured SOCKS5 proxy, then run `python3 aidm_gui.py`.
2. With clean application settings, confirm empty host/port fields and example helper text.
3. Enter and Save the actual endpoint, enable Proxy Mode, and check the main indicator.
4. Try one known-compatible direct URL, media page, and Inspector HLS/DASH handoff as data allows.
5. Turn mode OFF during a transfer: the active job must continue unchanged; drawer state must sync.
   Abort/fail and Retry it: the original proxy endpoint must still be used.
6. Configure a new download while OFF and verify normal routing returns.
7. Restart: mode/indicator must be OFF/hidden, with saved host/port restored.
8. With an unavailable endpoint, confirm failure with no direct fallback. Check bulk/playlist
   rejection and native desktop focus/theme appearance. These live checks remain deferred.

Cross-project architecture source of truth: [Linux_Mint ecosystem document](https://github.com/asif-AiML/Linux_Mint/blob/master/Architecture/AiDM-Psiphon-Ecosystem.md).
