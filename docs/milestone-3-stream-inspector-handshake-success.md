# Milestone 3 — First Successful Stream Inspector → AiDM Handshake

**Date:** 2026-09-25  
**Branch:** `integration/aidm-unified-router`

## Why this milestone matters

This milestone records the first successful real-world handshake between the **AiDM Stream Inspector browser extension** and **AiDM**.

For roughly two months, the project had been working toward this exact moment: a browser-observed streaming session supplying the context that a naked stream URL alone could not provide, and AiDM successfully carrying that context into its existing downloader path.

This was not only a parser or mocked-command success. It was a real browser-session test.

---

## The control case: naked URL failed

The same streaming session was first tested with the naked HLS URL only.

Conceptually:

```text
Naked HLS URL
    ↓
AiDM
    ↓
stream request without browser-observed context
    ↓
FAILED
```

This result was important because it established the baseline for the experiment.

The media URL by itself was not sufficient for this session.

---

## The Stream Inspector-assisted case

The browser extension was then used on the same session.

The extension supplied the selected media candidate together with the browser-observed handoff data that AiDM had been designed to accept:

```text
selected HLS URL
+ User-Agent
+ Referer
+ title
    ↓
AiDM argument parser
    ↓
normalized StreamInput
    ↓
stream detection with captured request context
    ↓
yt-dlp native HLS downloader
```

The real run reached the expected stream path and printed:

```text
Input type: HLS stream
Extractor/downloader: yt-dlp native
Post-processing: FFmpeg when required
```

yt-dlp then successfully parsed the HLS playlist:

```text
[hlsnative] Total fragments: 1371
```

It created the destination using the title supplied through the Stream Inspector handoff:

```text
[download] Destination: FBOX _ Watch Spider-Man_ Brand New Day 2026 Online Free on Fboxtv.mp4
```

and began downloading:

```text
[download]   0.0% of ~   3.00GiB at   31.78KiB/s ETA 64:26:54 (frag 1/1371)
```

The full movie was intentionally not downloaded because the estimated size was about 3 GiB. That was unnecessary for this milestone: by this point yt-dlp had already accepted the request, parsed the playlist, discovered 1371 fragments, selected the expected destination name, and begun fragment download.

---

## What the test proved

The successful run demonstrated the complete main-media handoff:

```text
Browser streaming session
        ↓
AiDM Stream Inspector
        ↓
POSIX-shell-safe exported arguments
        ↓
AiDM argparse
        ↓
Inspector invocation recognized
        ↓
StreamInput
  ├─ selected media URL
  ├─ captured User-Agent
  ├─ captured Referer
  └─ title
        ↓
stream probe
        ↓
HLS classification
        ↓
yt-dlp native
        ↓
download started successfully
```

Specifically, the test provided real-world evidence that:

- the Stream Inspector-selected media URL reached AiDM;
- browser-observed request context could make a session work where the naked URL failed;
- captured request headers reached the streaming path;
- the Inspector title reached AiDM's filename sanitization/output-template path;
- yt-dlp successfully parsed the protected HLS playlist;
- the existing naked-stream architecture remained separate from Inspector-assisted handling;
- the browser extension and AiDM now function as two connected parts of one download workflow.

---

## Why the failed naked URL makes this result stronger

The most meaningful part of the test was not simply that the Inspector-assisted command worked.

The same session provided both a baseline and an assisted case:

```text
Naked URL only
→ failed

Same session + Stream Inspector context
→ HLS recognized
→ 1371 fragments found
→ output name created
→ download began
```

That distinction matters architecturally.

The Stream Inspector was not merely adding cosmetic metadata. In this real session, the browser-observed context was the difference between the naked stream attempt failing and the AiDM download path proceeding successfully.

This directly validates the original reason for building a dedicated browser extension instead of relying only on copied streaming URLs.

---

## Title handoff also passed

The generated destination:

```text
FBOX _ Watch Spider-Man_ Brand New Day 2026 Online Free on Fboxtv.mp4
```

confirmed that the title exported by the extension was accepted by AiDM and used for output naming.

The intended title flow is therefore proven end-to-end:

```text
browser page title
→ Stream Inspector export
→ argparse
→ StreamInput.title
→ AiDM sanitize_filename()
→ yt-dlp -o template
→ destination filename
```

---

## The HLS warning

yt-dlp also emitted:

```text
WARNING: Live HLS streams are not supported by the native downloader. If this is a livestream, please add "--downloader ffmpeg --hls-use-mpegts" to your command
```

For this test the warning was harmless.

Immediately afterward, the native HLS downloader successfully discovered 1371 fragments and began downloading them.

The warning is therefore recorded as a future terminal-output/polish concern, not as a Milestone 3 failure.

AiDM should not switch downloader behavior merely to silence this warning without separate testing, especially because earlier FFmpeg fallback experiments produced worse results and were intentionally reverted.

---

## Milestone 3 status

```text
Milestone 3A ✅ Inspector route boundary
Milestone 3B ✅ Main-media context wiring
Milestone 3C ✅ Command/context validation
Milestone 3D ✅ Real browser → Stream Inspector → AiDM → yt-dlp test

Milestone 3 ✅ COMPLETE
```

This is the first point in the project where the full intended browser-assisted streaming architecture was demonstrated against a real session.

---

## Historical significance

AiDM originally reached streaming URLs without having enough browser-session context to use them reliably. That limitation was one of the reasons the project eventually expanded beyond a downloader and gained its own browser extension.

After repeated work on:

- stream detection;
- HLS/DASH handling;
- expiring/signed URLs;
- User-Agent and Referer preservation;
- removal of the old pipe-delimited detector grammar;
- browser traffic intelligence;
- candidate ranking;
- Stream Inspector export formatting;
- unified AiDM routing;
- parser integration;
- normalized `StreamInput`;
- and downloader header/title plumbing;

the two sides finally met successfully in a real download path.

The architecture that had previously existed only as a design is now demonstrated:

```text
Browser
→ Stream Inspector
→ AiDM
→ yt-dlp
→ media fragments
```

For the project, this is a major turning point: **Stream Inspector is no longer only detecting useful streaming data. AiDM can now use that data successfully.**
