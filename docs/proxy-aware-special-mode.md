# Proxy-aware special mode — AiDM design decision

**Status:** planned, not implemented. **Branch:** `feat/controls-settings`. **Scope:** AiDM only.

## Motivation and evidence

A user tested the independent `yt-dlp` command below while the **standalone Psiphon-Linux** tunnel was running:

```bash
yt-dlp --proxy "socks5h://127.0.0.1:1081" "URL"
```

With a URL from a website normally blocked by the ISP, the download **started and completed**. This establishes that this yt-dlp + Psiphon SOCKS5 route works for the tested URL/session, not that every site or media type will work or that AiDM integration has already passed.

**Decision:** Do **not** embed or bundle the Psiphon engine in AiDM. Instead add an **occasional, opt-in, provider-neutral SOCKS5 special mode**, usable with an independently running Psiphon-Linux instance or another compatible proxy (e.g. Tor). Normal AiDM must not depend on either provider.

## GUI specification

Place an optional **Proxy-aware special mode** section in AiDM's existing settings UI (see `download-controls-settings-plan.md`).

- Two input fields: **SOCKS host** and **port**; example `127.0.0.1` and `1081`.
- **Save** stores validated host/port persistently for future launches. This explicit Save action is a **special-mode exception** to the current automatic-save rule for ordinary download controls; do not silently alter those controls.
- Independent **ON/OFF** switch; default **OFF** for new installations. ON never launches Psiphon or modifies Linux system/browser proxy settings.
- Saved address remains available while OFF. Enablement policy across restarts should be explicitly decided during implementation; the safe default is OFF on fresh installation and no implicit proxy activation.
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
| Other download controls | Existing behavior | Only minimal compatible single-download settings; unsupported controls unavailable |

The user intentionally calls this an **occasional special weapon**, not a parallel implementation of the complete downloader. Do **not** build new playlist, bulk, HLS/DASH parsing, subtitle, concurrency or parallel-control architectures solely for this mode. Existing yt-dlp stream extraction can be reused; one supported stream can still be downloaded. Explicitly suppress playlist traversal (e.g. appropriate yt-dlp `--no-playlist` behavior) and reject unsupported multi-URL inputs before launching.

Browser-captured context (e.g. Referer and User-Agent, where available) should be passed to yt-dlp as it is in the existing handoff. A proxied request is not a substitute for valid tokens, cookies, referer or permitted access.

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
- The successful manual yt-dlp test is **evidence**, not an implemented AiDM feature.

Cross-project architecture source of truth: [Linux_Mint ecosystem document](https://github.com/asif-AiML/Linux_Mint/blob/master/Architecture/AiDM-Psiphon-Ecosystem.md).
