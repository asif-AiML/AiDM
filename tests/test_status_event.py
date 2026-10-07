"""The shared status contract needs no Qt, UI text, logs or progress fields."""
import builtins
from dataclasses import fields, FrozenInstanceError
import runpy
import unittest
from unittest.mock import patch

import status_event
from status_event import StatusEvent, StatusKind, StatusReason


class StatusEventTests(unittest.TestCase):
    def test_model_imports_without_qt(self):
        original_import = builtins.__import__

        def without_qt(name, *args, **kwargs):
            if name.startswith(("PySide", "PyQt")):
                raise AssertionError("Status model must not import Qt")
            return original_import(name, *args, **kwargs)

        # Execute the module afresh even when other GUI tests already imported Qt.
        with patch("builtins.__import__", side_effect=without_qt):
            namespace = runpy.run_path(status_event.__file__)
        self.assertIn("StatusEvent", namespace)

    def test_immutable_semantic_payload_has_no_progress_or_raw_log_fields(self):
        event = StatusEvent(StatusKind.FAILED, "aria2c", StatusReason.START_FAILED)
        with self.assertRaises(FrozenInstanceError):
            event.engine = "changed"
        self.assertEqual([field.name for field in fields(event)], ["kind", "engine", "reason"])
        self.assertEqual(set(StatusKind), {StatusKind.STARTING_ENGINE, StatusKind.DOWNLOADING,
                                          StatusKind.COMPLETE, StatusKind.FAILED,
                                          StatusKind.ABORTING, StatusKind.ABORTED,
                                          StatusKind.DOWNLOADING_VIDEO, StatusKind.DOWNLOADING_AUDIO,
                                          StatusKind.MERGING, StatusKind.CONVERTING_AUDIO,
                                          StatusKind.REMUXING, StatusKind.FINALIZING})


if __name__ == "__main__":
    unittest.main()
