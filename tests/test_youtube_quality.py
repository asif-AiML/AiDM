"""Persistent backend quality regressions; no network or real downloads."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import aidm
import youtube


class YouTubeQualityTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        redirect = redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        for target in ["subprocess.run", "subprocess.Popen", "urllib.request.urlopen"]:
            guard = patch(target, side_effect=AssertionError(f"Unexpected execution: {target}"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_single_video_selects_quality_once(self):
        urls = ["https://youtu.be/abcdefghijk"]
        with patch("builtins.input", side_effect=["1", "2"]) as prompt, \
                patch.object(youtube, "get_available_youtube_qualities", return_value=[1080, 720]) as discover, \
                patch.object(youtube, "download_youtube_video", return_value=0) as download:
            self.assertEqual(youtube.download_youtube(urls), 0)
        discover.assert_called_once_with(urls[0])
        download.assert_called_once_with(urls, max_height=720)
        self.assertEqual(prompt.call_count, 2)
        self.assertIn("Available video qualities:", self.output.getvalue())

    def test_bulk_uses_first_normalized_url_and_one_selector(self):
        raw = ["https://www.youtube.com/watch?v=abcdefghijk&list=example",
               "https://youtu.be/lmnopqrstuv?si=tracking"]
        normalized = ["https://www.youtube.com/watch?v=abcdefghijk", "https://youtu.be/lmnopqrstuv"]
        with patch("builtins.input", side_effect=["1", "1"]) as prompt, \
                patch.object(youtube, "get_available_youtube_qualities", return_value=[1080, 720]) as discover, \
                patch.object(youtube, "download_youtube_video", return_value=0) as download:
            self.assertEqual(aidm.run_from_args(aidm.parse_args(raw)), 0)
        discover.assert_called_once_with(normalized[0])
        download.assert_called_once_with(normalized, max_height=1080)
        self.assertEqual(prompt.call_count, 2)

    def test_discovery_failure_continues_with_best_for_single_and_bulk(self):
        for urls in [["first"], ["first", "second"]]:
            with self.subTest(urls=urls), \
                    patch.object(youtube, "choose_youtube_mode", return_value="video"), \
                    patch.object(youtube, "get_available_youtube_qualities", return_value=[]) as discover, \
                    patch.object(youtube, "choose_youtube_quality") as choose, \
                    patch.object(youtube, "download_youtube_video", return_value=7) as download:
                self.assertEqual(youtube.download_youtube(urls), 7)
                discover.assert_called_once_with("first")
                choose.assert_not_called()
                download.assert_called_once_with(urls, max_height=None)
        self.assertIn("Could not determine YouTube video qualities; using best available quality.", self.output.getvalue())

    def test_audio_and_wav_skip_quality_and_preserve_commands(self):
        for selection, extra in [("2", []), ("3", ["--extract-audio", "--audio-format", "wav"])]:
            for urls in [["first"], ["first", "second"]]:
                with self.subTest(selection=selection, urls=urls), \
                        patch("builtins.input", return_value=selection) as prompt, \
                        patch.object(youtube, "get_available_youtube_qualities") as discover, \
                        patch.object(youtube, "choose_youtube_quality") as choose, \
                        patch.object(youtube, "run_command", return_value=0) as run:
                    self.assertEqual(youtube.download_youtube(urls), 0)
                    discover.assert_not_called()
                    choose.assert_not_called()
                    prompt.assert_called_once()
                    run.assert_called_once_with(
                        youtube.build_youtube_command(len(urls)) + ["-f", "bestaudio/best"] + extra + urls
                    )

    def test_format_height_limit_and_mp4_preference(self):
        for height in [None, 480, 1080]:
            with self.subTest(height=height):
                expression = youtube.build_youtube_format(height)
                branches = expression.split("/")
                self.assertEqual(len(branches), 3)
                self.assertIn("ba[ext=m4a]", branches[0])
                self.assertTrue(branches[1].endswith("+ba"))
                for branch in branches:
                    if height is not None:
                        self.assertIn(f"[height<={height}]", branch)
                    else:
                        self.assertNotIn("height", branch)
                command = youtube.build_youtube_video_command(height)
                self.assertEqual(command[command.index("--format-sort") + 1], "res,ext:mp4:m4a")

    def assert_video_policy(self, command, height):
        for option in ["--merge-output-format", "--remux-video"]:
            self.assertEqual(command.count(option), 1)
            self.assertEqual(command[command.index(option) + 1], "mp4")
        self.assertEqual(command[command.index("-f") + 1], youtube.build_youtube_format(height))
        for forbidden in ["--recode-video", "--postprocessor-args", "-c:v", "libx264"]:
            self.assertNotIn(forbidden, command)

    def test_video_api_applies_one_format_to_all_urls(self):
        for height in [None, 720, 1080]:
            with self.subTest(height=height), patch.object(youtube, "run_command", return_value=9) as run:
                for urls in [["first"], ["first", "second"]]:
                    run.reset_mock()
                    self.assertEqual(youtube.download_youtube_video(urls, max_height=height), 9)
                    run.assert_called_once_with(youtube.build_youtube_video_command(height, len(urls)) + urls)
                    self.assert_video_policy(run.call_args.args[0], height)

    def test_playlist_selected_and_fallback_commands_unchanged(self):
        for qualities, height in [([1080, 720], 720), ([], None)]:
            with self.subTest(qualities=qualities), \
                    patch.object(youtube, "get_available_youtube_qualities", return_value=qualities) as discover, \
                    patch.object(youtube, "choose_youtube_quality", return_value=height) as choose, \
                    patch.object(youtube, "choose_youtube_mode") as mode, \
                    patch.object(youtube, "run_command", return_value=0) as run:
                self.assertEqual(youtube.download_youtube_playlist("playlist"), 0)
                discover.assert_called_once_with("playlist")
                if qualities:
                    choose.assert_called_once_with(qualities)
                else:
                    choose.assert_not_called()
                mode.assert_not_called()
                run.assert_called_once_with(youtube.build_youtube_video_command(height) + ["--yes-playlist", "playlist"])
                self.assert_video_policy(run.call_args.args[0], height)
        self.assertIn("Could not determine playlist qualities; using best available quality.", self.output.getvalue())

    def test_shared_discovery_handles_video_and_playlist_metadata(self):
        formats = [{"height": h, "vcodec": codec} for h, codec in [
            (720, "avc1"), (1080, "vp9"), (720, "avc1"), (2160, "none"),
            (None, "none"), (True, "avc1"), (-1, "avc1"),
        ]]
        for info in [{"formats": formats}, {"entries": [{"formats": formats}]}]:
            with self.subTest(info=info), patch.object(youtube.subprocess, "run", return_value=Mock(
                returncode=0, stdout=json.dumps(info)
            )) as probe:
                self.assertEqual(youtube.get_available_youtube_qualities("source"), [1080, 720])
                probe.assert_called_once_with(
                    ["yt-dlp", "--dump-single-json", "--skip-download", "--playlist-items", "1", "source"],
                    capture_output=True, text=True, check=False,
                )

    def test_shared_discovery_failures_are_nonfatal(self):
        for response in [Mock(returncode=1), Mock(returncode=0, stdout="invalid"),
                         Mock(returncode=0, stdout="[]"), Mock(returncode=0, stdout='{"formats": []}')]:
            with patch.object(youtube.subprocess, "run", return_value=response):
                self.assertEqual(youtube.get_available_youtube_qualities("source"), [])
        with patch.object(youtube.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(youtube.get_available_youtube_qualities("source"), [])

    def test_quality_selector_retries_invalid_choices(self):
        with patch("builtins.input", side_effect=["bad", "0", "3", "2"]) as prompt:
            self.assertEqual(youtube.choose_youtube_quality([1080, 720]), 720)
            self.assertEqual(prompt.call_count, 4)


@unittest.skipUnless(shutil.which("yt-dlp"), "Offline selection fixtures require yt-dlp")
class OfflineFormatSelectionTests(unittest.TestCase):
    """Exercise actual yt-dlp sorting, without fetching or downloading media."""

    def test_resolution_before_container_and_native_preference(self):
        def video(name, height, ext, audio=False):
            return dict(format_id=name, height=height, width=height * 16 // 9,
                        ext=ext, vcodec="avc1" if ext == "mp4" else "vp9",
                        acodec=("aac" if ext == "mp4" else "opus") if audio else "none",
                        url=f"https://example.invalid/{name}.{ext}")

        aac = dict(format_id="aac", ext="m4a", vcodec="none", acodec="mp4a.40.2",
                   url="https://example.invalid/audio.m4a")
        opus = dict(format_id="audio-opus", ext="webm", vcodec="none", acodec="opus",
                    url="https://example.invalid/audio.webm")
        cases = [
            (None, [video("native", 1080, "mp4"), video("high", 2160, "webm"), aac, opus], "high+aac"),
            (1080, [video("native", 480, "mp4"), video("high", 1080, "webm"), aac], "high+aac"),
            (1080, [video("native", 1080, "mp4"), video("other", 1080, "webm"), aac, opus], "native+aac"),
            (480, [video("native", 480, "mp4"), video("high", 1080, "webm"), aac], "native+aac"),
            (1080, [video("lower", 720, "webm"), opus], "lower+audio-opus"),
            (480, [video("combined", 480, "webm", True)], "combined"),
            (None, [video("native", 1080, "mp4"), video("combined", 2160, "webm", True), aac], "combined"),
        ]
        with TemporaryDirectory(prefix="aidm-format-") as directory:
            fixture = Path(directory) / "fixture.json"
            for height, formats, expected in cases:
                with self.subTest(height=height, expected=expected):
                    fixture.write_text(json.dumps({"id": "fixture", "title": "Fixture", "formats": formats,
                                                   "extractor": "generic", "extractor_key": "Generic"}))
                    # The common downloader args aren't needed in simulation;
                    # retain all video policy args from the production helper.
                    policy = youtube.build_youtube_video_command(height)[len(youtube.build_youtube_command()):]
                    completed = subprocess.run([
                        "yt-dlp", "--ignore-config", "--no-plugin-dirs", "--no-cache-dir",
                        "--simulate", "--no-check-formats", "--load-info-json", str(fixture),
                        "--print", "%(format_id)s",
                        *policy,
                    ], capture_output=True, text=True, timeout=15, cwd=directory)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout.strip(), expected)
                    self.assertEqual([p.name for p in Path(directory).iterdir()], ["fixture.json"])


if __name__ == "__main__":
    unittest.main()
