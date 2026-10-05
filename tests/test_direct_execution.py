"""Shared direct command policy and unchanged CLI dispatch; no downloads."""
import unittest
from unittest.mock import patch

import aidm
import downloader
from inspection import InputKind, InspectionResult


class DirectCommandTests(unittest.TestCase):
    URL = "https://example.test/file.zip?token=a%2Fb&value=1"
    FLAGS = ["aria2c", "--continue=true", "--max-connection-per-server=1",
             "--split=1", "--min-split-size=1M", "--console-log-level=warn",
             "--summary-interval=1"]

    def test_cli_command_preserves_original_flags_and_cwd(self):
        self.assertEqual(downloader.build_direct_command(self.URL), self.FLAGS + [self.URL])

    def test_gui_destination_is_one_argument_without_cwd_change(self):
        with patch("os.chdir", side_effect=AssertionError("cwd must not change")):
            self.assertEqual(downloader.build_direct_command(self.URL, "/tmp/example folder"),
                             self.FLAGS + ["--dir=/tmp/example folder", self.URL])

    def test_blocking_cli_wrapper_reuses_builder_and_returns_exit_code(self):
        for destination in (None, "/tmp/example"):
            with patch.object(downloader, "build_direct_command", return_value=["fixture"]) as build, \
                    patch.object(downloader, "run_command", return_value=7) as run:
                self.assertEqual(downloader.download_direct(self.URL, destination), 7)
                build.assert_called_once_with(self.URL, destination)
                run.assert_called_once_with(["fixture"])

    def test_cli_route_supplies_no_destination(self):
        result = InspectionResult(InputKind.DIRECT_SINGLE, [self.URL])
        with patch.object(aidm, "classify_input", return_value=result), \
                patch.object(aidm, "download_direct", return_value=0) as download:
            self.assertEqual(aidm.run_from_args(aidm.parse_args([self.URL])), 0)
            download.assert_called_once_with(self.URL)
