# Milestone 16 bulk item-start captures

Actual stdout from yt-dlp **2026.08.19**, using three supplied loopback HTTP
URLs in one invocation, not a playlist. Media consisted of three copies of the
generated three-second combined MP4 from the Milestone 15 fixture investigation.
No internet media or YouTube account was used. Tests replay these files offline.

Production builders used `total_videos=3`, `telemetry=True`, and an explicit
destination. Video used BEST because generic direct local URLs do not expose
height metadata for a height filter. Audio used `bestaudio/best` (the combined
MP4 fallback here); WAV used that same selector plus extraction to WAV. Local
capture overrides were `--ignore-config --no-plugin-dirs --no-cache-dir`.
Each command ended in `--no-playlist -- URL1 URL2 URL3`.

The production GUI item template is:

```
before_dl:AIDM_ITEM:%(.{video_autonumber,title})j
```

The dictionary projection safely quotes titles as JSON. `video_autonumber` was
1, 2, 3 across the supplied URLs. Total is deliberately absent from the template;
the immutable job's URL count is authoritative. All four commands exited zero:

- `video.txt`: three MP4 outputs through the shared video builder.
- `original.txt`: three untouched combined MP4 fallbacks, without conversion.
- `wav.txt`: three WAV outputs, with ExtractAudio before item advancement.
- `retry.txt`: second run of the video command in the same destination; existing
  files were recognized and the same three item-start records still appeared.

These captures validate actual template/framing, sequencing and skip behavior,
not YouTube extraction or every possible failure/skip policy. An extraction
failure before `before_dl` supplies no item-start record; no identity is invented.
Overall nonzero exit remains FAILED regardless of any later item records.

Reference: [yt-dlp output-template fields](https://github.com/yt-dlp/yt-dlp#output-template).
