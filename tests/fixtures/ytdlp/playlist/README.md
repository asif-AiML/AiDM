# Playlist item template verification

`items.txt` was captured from installed yt-dlp **2026.08.19** on 2026-10-07.
The actual `YoutubeDL.process_ie_result` playlist traversal processed three
pre-resolved synthetic video entries, with `skip_download=True`, `quiet=True`,
`cachedir=False`, a temporary output directory, and:

```python
forceprint = {'before_dl': ['AIDM_ITEM:%(.{playlist_autonumber,n_entries,title})j']}
```

The fixture playlist had title `Stable Playlist`; its entries were `First`,
`Second é`, and `Third`, with IDs 1–3 and non-contacted example.invalid MP4 URLs.
No extraction, network request, media download, or post-processing was required.
This verifies real template JSON output and queue indexing, not live YouTube
availability. The persistent test parses the captured output offline.

Installed `YoutubeDL.__process_playlist` assigns `playlist_autonumber = i + 1`
from playlist traversal; `video_autonumber` is a separate processed-video counter.
See the upstream output template fields:
https://github.com/yt-dlp/yt-dlp#output-template

Known DownloadJob.item_count takes priority over runtime n_entries. Runtime
n_entries supplies a total only when inspection could not determine it.
