import unittest

from download_job import (
    BulkMode,
    DownloadJob,
    VideoQuality,
    YouTubeMode,
    build_download_job,
)
from inspection import InputKind, InspectionResult
from stream_parser import StreamInput


class DownloadJobTests(unittest.TestCase):
    def test_youtube_single_modes(self):
        result = InspectionResult(
            kind=InputKind.YOUTUBE_SINGLE,
            urls=["https://www.youtube.com/watch?v=abcdefghijk"],
        )
        for mode in (
            YouTubeMode.VIDEO,
            YouTubeMode.ORIGINAL_AUDIO,
            YouTubeMode.WAV,
        ):
            with self.subTest(mode=mode):
                quality = 1080 if mode == YouTubeMode.VIDEO else None
                job = build_download_job(result, mode=mode, video_quality=quality)
                self.assertEqual(job.video_quality, quality)
                self.assertEqual(job.kind, InputKind.YOUTUBE_SINGLE)
                self.assertEqual(job.mode, mode)
                self.assertEqual(job.urls, tuple(result.urls))

    def test_youtube_bulk_modes(self):
        urls = [
            "https://www.youtube.com/watch?v=abcdefghijk",
            "https://www.youtube.com/watch?v=lmnopqrstuv",
        ]
        result = InspectionResult(kind=InputKind.YOUTUBE_BULK, urls=urls)
        for mode in (
            YouTubeMode.VIDEO,
            YouTubeMode.ORIGINAL_AUDIO,
            YouTubeMode.WAV,
        ):
            with self.subTest(mode=mode):
                quality = 720 if mode == YouTubeMode.VIDEO else None
                job = build_download_job(result, mode=mode, video_quality=quality)
                self.assertEqual(job.video_quality, quality)
                self.assertEqual(job.kind, InputKind.YOUTUBE_BULK)
                self.assertEqual(job.mode, mode)
                self.assertEqual(job.urls, tuple(urls))

    def test_youtube_video_quality(self):
        result = InspectionResult(
            kind=InputKind.YOUTUBE_PLAYLIST,
            urls=["https://www.youtube.com/playlist?list=PL123"],
        )
        for quality in (1080, VideoQuality.BEST):
            with self.subTest(quality=quality):
                job = build_download_job(result, video_quality=quality)
                self.assertEqual(job.video_quality, quality)

    def test_direct_single_has_no_pre_download_title(self):
        result = InspectionResult(
            kind=InputKind.DIRECT_SINGLE,
            urls=["https://example.com/software.exe"],
            title="software.exe",
        )
        job = build_download_job(result)
        self.assertEqual(job.kind, InputKind.DIRECT_SINGLE)
        self.assertIsNone(job.title)

    def test_direct_bulk_modes(self):
        urls = [
            "https://example.com/a.zip",
            "https://example.com/b.zip",
        ]
        result = InspectionResult(kind=InputKind.DIRECT_BULK, urls=urls)
        for mode in (BulkMode.SEQUENTIAL, BulkMode.PARALLEL):
            with self.subTest(mode=mode):
                job = build_download_job(result, bulk_mode=mode)
                self.assertEqual(job.bulk_mode, mode)
                self.assertEqual(job.urls, tuple(urls))

    def test_hls_and_dash_jobs(self):
        for kind, url in (
            (InputKind.HLS, "https://example.com/master.m3u8"),
            (InputKind.DASH, "https://example.com/manifest.mpd"),
        ):
            with self.subTest(kind=kind):
                job = build_download_job(InspectionResult(kind=kind, urls=[url]))
                self.assertEqual(job.kind, kind)
                self.assertEqual(job.urls, (url,))

    def test_generic_ytdlp_job(self):
        url = "https://example.com/watch/123"
        job = build_download_job(
            InspectionResult(kind=InputKind.GENERIC_YTDLP, urls=[url])
        )
        self.assertEqual(job.kind, InputKind.GENERIC_YTDLP)
        self.assertEqual(job.urls, (url,))

    def test_stream_inspector_preserves_context_and_subtitle_order(self):
        url = "https://cdn.example.com/master.m3u8?token=abc"
        subtitles = [
            "https://cdn.example.com/en.vtt",
            "https://cdn.example.com/ur.vtt",
            "https://cdn.example.com/en.vtt",
        ]
        stream = StreamInput(
            url=url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://example.com/player",
            },
            stream_type="hls",
            title="Example Movie",
            subtitles=list(subtitles),
        )
        result = InspectionResult(
            kind=InputKind.STREAM_INSPECTOR,
            urls=[url],
            stream=stream,
            route_kind=InputKind.HLS,
            title="Example Movie",
        )
        job = build_download_job(result)

        self.assertEqual(job.kind, InputKind.STREAM_INSPECTOR)
        self.assertEqual(job.route_kind, InputKind.HLS)
        self.assertEqual(job.urls, (url,))
        self.assertEqual(job.title, "Example Movie")
        self.assertEqual(dict(job.headers), stream.headers)
        self.assertEqual(job.subtitles, tuple(subtitles))

    def test_audio_modes_reject_quality(self):
        for kind in (InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK):
            urls = ["url", "url2"] if kind == InputKind.YOUTUBE_BULK else ["url"]
            for mode in (YouTubeMode.ORIGINAL_AUDIO, YouTubeMode.WAV):
                for quality in (720, VideoQuality.BEST):
                    with self.subTest(kind=kind, mode=mode, quality=quality), self.assertRaises(ValueError):
                        build_download_job(InspectionResult(kind, urls), mode=mode, video_quality=quality)

    def test_non_youtube_jobs_reject_quality(self):
        for kind in (InputKind.DIRECT_SINGLE, InputKind.DIRECT_BULK, InputKind.HLS,
                     InputKind.DASH, InputKind.GENERIC_YTDLP, InputKind.TORRENT):
            bulk = kind == InputKind.DIRECT_BULK
            for quality in (1080, VideoQuality.BEST):
                with self.subTest(kind=kind, quality=quality), self.assertRaises(ValueError):
                    build_download_job(InspectionResult(kind, ["a", "b"] if bulk else ["a"]),
                                       bulk_mode=BulkMode.PARALLEL if bulk else None, video_quality=quality)

    def test_video_requires_valid_explicit_quality(self):
        for kind in (InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_BULK, InputKind.YOUTUBE_PLAYLIST):
            result = InspectionResult(kind, ["a", "b"] if kind == InputKind.YOUTUBE_BULK else ["a"])
            mode = None if kind == InputKind.YOUTUBE_PLAYLIST else YouTubeMode.VIDEO
            for quality in (None, 0, -1, True, False, 1080.0, "1080"):
                with self.subTest(kind=kind, quality=quality), self.assertRaises(ValueError):
                    build_download_job(result, mode=mode, video_quality=quality)
            for quality in (360, 480, 720, 1080, 1440, 2160, VideoQuality.BEST):
                with self.subTest(kind=kind, quality=quality):
                    self.assertEqual(build_download_job(result, mode=mode, video_quality=quality).video_quality, quality)

    def test_inspector_youtube_quality_uses_underlying_route(self):
        for route in (InputKind.YOUTUBE_SINGLE, InputKind.YOUTUBE_PLAYLIST):
            stream = StreamInput("https://youtube.com/watch?v=exact&token=a%2Fb", title="Canonical",
                                 headers={"User-Agent": "UA"}, subtitles=["sub", "sub"])
            result = InspectionResult(InputKind.STREAM_INSPECTOR, [stream.url], stream=stream, route_kind=route)
            mode = YouTubeMode.VIDEO if route == InputKind.YOUTUBE_SINGLE else None
            with self.assertRaises(ValueError):
                build_download_job(result, mode=mode)
            job = build_download_job(result, mode=mode, video_quality=1080)
            self.assertEqual(job.urls, (stream.url,))
            self.assertEqual(job.title, "Canonical")
            self.assertEqual(job.subtitles, ("sub", "sub"))
            self.assertEqual(job.headers, stream.headers)
            self.assertEqual(job.video_quality, 1080)
            with self.assertRaises(ValueError):
                build_download_job(result, mode=YouTubeMode.WAV, video_quality=1080)

    def test_playlist_rejects_audio_mode(self):
        result = InspectionResult(
            kind=InputKind.YOUTUBE_PLAYLIST,
            urls=["https://www.youtube.com/playlist?list=PL123"],
        )
        with self.assertRaises(ValueError):
            build_download_job(
                result,
                mode=YouTubeMode.WAV,
                video_quality=720,
            )

    def test_direct_single_rejects_bulk_mode(self):
        result = InspectionResult(
            kind=InputKind.DIRECT_SINGLE,
            urls=["https://example.com/file.iso"],
        )
        with self.assertRaises(ValueError):
            build_download_job(result, bulk_mode=BulkMode.PARALLEL)

    def test_direct_bulk_requires_multiple_urls(self):
        with self.assertRaises(ValueError):
            DownloadJob(
                kind=InputKind.DIRECT_BULK,
                urls=("https://example.com/file.iso",),
                bulk_mode=BulkMode.SEQUENTIAL,
            )

    def test_stream_inspector_requires_single_url(self):
        with self.assertRaises(ValueError):
            DownloadJob(
                kind=InputKind.STREAM_INSPECTOR,
                urls=("https://example.com/a", "https://example.com/b"),
                route_kind=InputKind.HLS,
            )

    def test_generic_ytdlp_rejects_youtube_mode(self):
        with self.assertRaises(ValueError):
            DownloadJob(
                kind=InputKind.GENERIC_YTDLP,
                urls=("https://example.com/watch/123",),
                mode=YouTubeMode.VIDEO,
            )


if __name__ == "__main__":
    unittest.main()
