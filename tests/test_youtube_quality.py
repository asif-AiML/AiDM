"""Persistent backend quality regressions; no network or real downloads."""

from contextlib import redirect_stdout
import io
import json
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

    def test_format_height_limit_and_original_default(self):
        self.assertEqual(youtube.build_youtube_format(1080), "bv[height<=1080]+ba/b[height<=1080]")
        self.assertEqual(youtube.build_youtube_format(None), "bv*[vcodec^=vp09]+ba[acodec=opus]/bv*+ba/b")

    def test_video_api_applies_one_format_to_all_urls(self):
        for height in [None, 720, 1080]:
            with self.subTest(height=height), patch.object(youtube, "run_command", return_value=9) as run:
                urls = ["first", "second"]
                self.assertEqual(youtube.download_youtube_video(urls, max_height=height), 9)
                run.assert_called_once_with(
                    youtube.build_youtube_command(2) + ["-f", youtube.build_youtube_format(height)] + urls
                )

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
                run.assert_called_once_with(youtube.build_youtube_command() + [
                    "--yes-playlist", "-f", youtube.build_youtube_format(height),
                    "--merge-output-format", "mp4", "playlist",
                ])
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


if __name__ == "__main__":
    unittest.main()
