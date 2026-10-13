# YouTube audio formats and embedded thumbnails

This extends the existing YouTube workflow on `feat/youtube-thumbnails`.
It supersedes the historical flat Video / Original Audio / WAV configuration
described in earlier GUI milestones. No playlist audio support is introduced.

## Configuration and GUI transitions

After classification, the existing Download action opens configuration. Neither
Video nor Audio is selected. Video starts the existing cancellable quality
lookup, preserving the explicit resolution selector and best-available fallback.
Audio reveals Original Best, FLAC, MP3, and WAV without a quality lookup or
default format. Selecting a format reveals the artwork checkbox, initially off.
WAV disables and clears it; switching back to a compatible format leaves it off.
Switching Video/Audio clears audio settings and video quality, invalidates the
old lookup generation, and rebuilds the job only after required choices exist.
The existing layout/size-hint resizing and native keyboard controls are reused.

The CLI asks Video/Audio, then audio format, then optional artwork (except WAV).
Invalid answers repeat the appropriate prompt; Enter at the artwork prompt means
No. A URL-list batch receives one configuration and retains the existing
sequential yt-dlp execution. Each item uses its own metadata and thumbnail.
Retry uses the original immutable job, including destination, format, and artwork.

## Shared backend and commands

`DownloadJob` adds explicit `AudioFormat` and `embed_thumbnail` fields. Validation
rejects incomplete audio choices, audio/video quality conflicts, WAV artwork,
and audio settings on playlists or unrelated routes. Existing programmatic
ORIGINAL_AUDIO/WAV modes and the `wav=True` builder remain compatible; the new
frontends use AUDIO plus an explicit format.

Both frontends use `build_youtube_audio_command()` in `youtube.py`:

| Format | Selection and conversion | Artwork |
| --- | --- | --- |
| Original Best | Existing `-f bestaudio/best`; no extraction or transcoding | Compatible source containers only |
| FLAC | Same source, `--extract-audio --audio-format flac` | Optional |
| MP3 | Same source, `--extract-audio --audio-format mp3 --audio-quality 0` | Optional |
| WAV | Existing `--extract-audio --audio-format wav` | Disabled |

FLAC, MP3, and artwork-enabled output use `--embed-metadata`. Source selection,
aria2c arguments, native DASH/HLS delegation, video command policy, CLI working
directory, and GUI `-P` destination handling remain in the existing builders.

Artwork adds an explicit local yt-dlp postprocessor from `ytdlp_plugins/`, running
at `after_move`, after conversion and metadata. Keep that directory with the
application when distributing/copying it. The installed yt-dlp executable loads
it directly, so AiDM's Python environment does not need the yt-dlp Python package.

The wrapper downloads this item's preferred thumbnail using yt-dlp's networking,
validates/normalizes the image with FFmpeg, and calls yt-dlp's EmbedThumbnail
processor on a temporary copy of the audio. For FLAC on yt-dlp builds without
optional Mutagen, the existing FFmpeg processor writes the picture using stream
copy. ffprobe checks for an attached picture before atomic replacement of the
original. This avoids a custom tagging library and new third-party dependencies.
Built-in `--embed-thumbnail` alone is insufficient: it can change WebM to MKV
and turn optional tagging errors into failed downloads. See
[yt-dlp's embedding implementation](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/postprocessor/embedthumbnail.py).

Missing, unavailable, invalid, unsupported, or failed artwork produces a warning
and leaves the completed audio intact. Download/conversion failures remain real
failures. GUI telemetry distinguishes conversion, artwork, finalization and
completion, without post-processing percentages. Artwork warnings remain visible
at completion, including when a later bulk item succeeds. Successful processing
leaves no thumbnail sidecars. CLI warnings are human-readable; GUI warning records
are fixed sentinels rather than parsed arbitrary error strings.

## Compatibility limits

- Original Best does not force M4A or change WebM into another container. WebM
  artwork is skipped. Other containers depend on installed yt-dlp/FFmpeg tagging
  support; Ogg/Opus embedding may require yt-dlp's optional Mutagen support.
- WAV has no promised broadly compatible cover-art workflow, so artwork is off.
- FLAC/WAV are lossless output encodings of a usually lossy source, not a source
  quality upgrade. MP3 conversion is another lossy encoding step.
- Safe artwork processing temporarily requires roughly one extra audio-file copy
  in the destination. Normal errors clean temporary files. A forced process kill
  may leave a hidden `.aidm-artwork-*` directory; the original audio is retained.
- Player and file-manager artwork rendering varies. No Android MX Player or
  Linux file-manager rendering verification is claimed.

## Linux Mint manual checks

From the repository root, check existing tools and run the automated suite:

```bash
git branch --show-current
yt-dlp --version
aria2c --version
ffmpeg -version
ffprobe -version
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests
python3 aidm_gui.py
```

The branch should be `feat/youtube-thumbnails`. In the GUI:

1. Paste a single YouTube URL and click Download. Verify neither mode is checked
   and no quality lookup starts. Choose Audio: no format is checked yet and the
   download action remains unavailable until a format is selected.
2. Choose each format. Verify artwork starts off; enable it for MP3/FLAC/Original.
   Switch to WAV: it must clear and disable artwork with explanatory text.
3. Choose Video, then quickly switch back to Audio while qualities are loading.
   A late quality result must not change Audio or enable downloading prematurely.
   Switch back to Video, choose a resolution, and verify the established workflow.
4. Download each audio format into a chosen folder. Check the extension, playback,
   title, cover presence where supported, and absence of thumbnail sidecars.
5. Paste two YouTube URLs. Choose one audio configuration, download, and confirm
   distinct titles/covers, sequential item counters, and completion. Abort during
   transfer or processing, then Retry; format, artwork, and folder must be retained.
6. Paste a playlist: only the established video-quality workflow should appear.
   Also check a direct file, direct sequential/parallel batch, and an Inspector
   command with a subtitle using known working inputs.

For CLI checks, supply accessible URLs you are permitted to download:

```bash
read -r -p 'First YouTube URL: ' YT_FIRST
read -r -p 'Second YouTube URL: ' YT_SECOND
python3 aidm.py "$YT_FIRST"
python3 aidm.py "$YT_FIRST" "$YT_SECOND"
```

Select `2` (Audio), then `1` Original / `2` FLAC / `3` MP3 / `4` WAV.
Enter `y` for compatible artwork, or Enter for off. WAV must skip that prompt.
The bulk command must ask only once. Also select `1` (Video) and confirm its
quality prompt is unchanged. Playlist CLI handling remains separate.

Inspect any resulting audio file independently:

```bash
read -r -p 'Output audio path: ' AUDIO_FILE
ffprobe -v error -show_format -show_streams -of json "$AUDIO_FILE"
ffmpeg -v error -i "$AUDIO_FILE" -map 0:a:0 -f null -
```

Expect the chosen audio codec, title metadata where added, an `attached_pic: 1`
stream when artwork succeeded, and successful audio decoding. Original WebM or
optional artwork failure should instead retain playable audio with a warning.

Automated file checks use synthetic audio and images through actual yt-dlp,
FFmpeg and ffprobe. File-URL fixtures override transfer to native locally;
production aria2c delegation is verified separately by command regressions.
These checks do not establish live YouTube availability or device artwork display.
