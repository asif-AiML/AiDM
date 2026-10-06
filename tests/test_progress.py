"""Offline telemetry contract, captured aria2c readouts and presentation tests."""
import builtins
from dataclasses import fields, FrozenInstanceError
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

import aria2_progress
from aria2_progress import Aria2ProgressParser, parse_aria2_progress
from gui_progress import format_bytes, format_eta, format_statistics
import progress_event
from progress_event import ProgressEvent


FIXTURES = Path(__file__).parent / "fixtures" / "aria2"
RECORD = b"[#6c63db 278528B/1048576B(26%) CN:1 DL:325383B ETA:2s]"


class ProgressTests(unittest.TestCase):
    def test_model_and_parser_import_without_qt(self):
        original = builtins.__import__

        def without_qt(name, *args, **kwargs):
            if name.startswith(("PySide", "PyQt")):
                raise AssertionError("Telemetry backend must not import Qt")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_qt):
            for module in (progress_event, aria2_progress):
                runpy.run_path(module.__file__)

    def test_frozen_full_partial_and_empty_events(self):
        event = ProgressEvent(43.7, 437, 1000, 100, 6)
        with self.assertRaises(FrozenInstanceError):
            event.percent = 90
        self.assertEqual(event.percent, 43.7)
        self.assertIsNone(ProgressEvent(downloaded_bytes=10).percent)
        self.assertIsNone(ProgressEvent(eta_seconds=0).total_bytes)
        self.assertTrue(all(getattr(ProgressEvent(), field.name) is None for field in fields(event)))
        self.assertEqual([field.name for field in fields(event)],
                         ["percent", "downloaded_bytes", "total_bytes", "speed_bytes_per_second", "eta_seconds"])

    def test_invalid_values_and_valid_zero(self):
        for value in (-.1, 100.1, float("nan"), float("inf"), True, "50"):
            with self.subTest(percent=value), self.assertRaises(ValueError):
                ProgressEvent(percent=value)
        for name in ("downloaded_bytes", "total_bytes", "speed_bytes_per_second", "eta_seconds"):
            for value in (-1, 1.5, True, "0"):
                with self.subTest(field=name, value=value), self.assertRaises(ValueError):
                    ProgressEvent(**{name: value})
            self.assertEqual(getattr(ProgressEvent(**{name: 0}), name), 0)

    def test_exact_captured_output_with_unrelated_summaries(self):
        events = Aria2ProgressParser().feed((FIXTURES / "exact.txt").read_bytes(), final=True)
        self.assertEqual(len(events), 8)  # Summary and readout duplicate each real snapshot.
        self.assertEqual(events[0], ProgressEvent(0, 0, 1048576, 0))
        self.assertEqual(events[2], ProgressEvent(26, 278528, 1048576, 325383, 2))
        self.assertEqual(events[-1], ProgressEvent(89, 933888, 1048576, 325283))

    def test_captured_binary_units_and_unknown_total(self):
        normal = Aria2ProgressParser().feed((FIXTURES / "normal.txt").read_bytes(), final=True)
        self.assertEqual(len(normal), 6)
        self.assertEqual(normal[0], ProgressEvent(31, 320 * 1024, 1048576, 315 * 1024, 2))
        unknown = Aria2ProgressParser().feed((FIXTURES / "unknown.txt").read_bytes(), final=True)
        self.assertEqual(len(unknown), 6)
        self.assertEqual(unknown[0], ProgressEvent(downloaded_bytes=320 * 1024,
                                                speed_bytes_per_second=317 * 1024))
        self.assertTrue(all(event.percent is None and event.total_bytes is None for event in unknown))

    def test_source_confirmed_gib_fractional_speed_and_eta_units(self):
        # Synthetic extended-unit cases, distinguished from captured fixtures.
        for eta, expected in (("23s", 23), ("2m15s", 135), ("1h02m", 3720),
                              ("1h2m3s", 3723), ("2h", 7200), ("0s", 0)):
            event = parse_aria2_progress(f"[#abcdef 1.5GiB/2.0GiB(75%) CN:1 DL:4.8MiB ETA:{eta}]")
            self.assertEqual(event, ProgressEvent(75, 1610612736, 2147483648, 5033164, expected))

    def test_no_percent_is_inferred_and_fractional_percent_is_preserved(self):
        event = parse_aria2_progress("[#abcdef 437B/1000B(43.7%) CN:1]")
        self.assertEqual(event, ProgressEvent(43.7, 437, 1000))
        self.assertIsNone(parse_aria2_progress("[#abcdef 437B/1000B CN:1]").percent)

    def test_every_chunk_boundary_cr_lf_multiple_and_final_tail(self):
        expected = parse_aria2_progress(RECORD.decode())
        for index in range(len(RECORD) + 1):
            parser = Aria2ProgressParser()
            self.assertEqual(parser.feed(RECORD[:index]), [])
            self.assertEqual(parser.feed(RECORD[index:] + b"\r"), [expected])
        parser = Aria2ProgressParser()
        self.assertEqual(parser.feed(RECORD + b"\r\n" + RECORD + b"\n" + RECORD), [expected, expected])
        self.assertEqual(parser.feed(b"", final=True), [expected])
        self.assertEqual(parser.feed(b"", final=True), [])
        parser = Aria2ProgressParser()
        events = []
        for byte in RECORD + b"\n":
            events.extend(parser.feed(bytes([byte])))
        self.assertEqual(events, [expected])

    def test_malformed_and_nonprogress_ignored_and_buffer_bounded(self):
        for line in ("WARNING: 10MiB at 99%", "[DL:4MiB]", "FILE: example.zip",
                     "[#abcdef 1B/2B(999%) CN:1]", "[#abcdef -1B/2B(50%) CN:1]",
                     "[#abcdef 1KB/2MB(50%) CN:1]", "[#abcdef 1B/2B(50%) CN:1 ETA:5s2h]",
                     "[#abcdef 1B/2B(50%) CN:1 DL:bad]", "prefix " + RECORD.decode(),
                     RECORD.decode()[:-1]):
            self.assertIsNone(parse_aria2_progress(line), line)
        parser = Aria2ProgressParser()
        self.assertEqual(parser.feed(b"x" * 100000), [])
        self.assertLessEqual(len(parser._buffer), parser.MAX_RECORD_BYTES)
        self.assertEqual(parser.feed(RECORD + b"\n"), [])  # Discard the oversized record's tail.
        self.assertEqual(len(parser.feed(RECORD + b"\n")), 1)

    def test_decimal_byte_speed_and_eta_formatting(self):
        for number, expected in ((0, "0 B"), (853, "853 B"), (1400, "1.4 KB"),
                                 (812000000, "812 MB"), (2100000000, "2.1 GB")):
            self.assertEqual(format_bytes(number), expected)
        for seconds, expected in ((0, "00:00"), (37, "00:37"), (277, "04:37"), (3723, "1:02:03")):
            self.assertEqual(format_eta(seconds), expected)
        self.assertEqual(format_statistics(ProgressEvent(56, 812000000, 2100000000, 4800000, 277)),
                         "4.8 MB/s • 812 MB / 2.1 GB • ETA 04:37")

    def test_partial_statistics_omit_unknown_fields(self):
        cases = [(ProgressEvent(), ""), (ProgressEvent(percent=10), ""),
                 (ProgressEvent(downloaded_bytes=812000000, total_bytes=2100000000), "812 MB / 2.1 GB"),
                 (ProgressEvent(downloaded_bytes=812000000, speed_bytes_per_second=4800000),
                  "4.8 MB/s • 812 MB downloaded"),
                 (ProgressEvent(total_bytes=1000), "1 KB total"),
                 (ProgressEvent(eta_seconds=37), "ETA 00:37"),
                 (ProgressEvent(speed_bytes_per_second=0, downloaded_bytes=0), "0 B/s • 0 B downloaded")]
        for event, expected in cases:
            self.assertEqual(format_statistics(event), expected)


if __name__ == "__main__":
    unittest.main()
