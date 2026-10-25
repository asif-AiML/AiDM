"""GUI text normalization and parser validation, without routing or Qt."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import shlex

from aidm import parse_args


@dataclass
class GuiInputResult:
    argv: list[str]
    args: argparse.Namespace | None = None
    error: str | None = None


def normalize_gui_input(text: str) -> list[str]:
    """Decode POSIX argument quoting; raise ValueError for incomplete quoting."""
    return shlex.split(text, comments=False, posix=True)


def validate_gui_input(text: str) -> GuiInputResult:
    """Validate parser grammar safely; success does not imply a runnable job."""
    try:
        argv = normalize_gui_input(text)
    except ValueError as error:
        return GuiInputResult(argv=[], error=str(error))

    if not argv:
        return GuiInputResult(argv=[])

    output = StringIO()
    errors = StringIO()
    try:
        with redirect_stdout(output), redirect_stderr(errors):
            args = parse_args(argv)
    except SystemExit as error:
        message = (
            "Help requested; enter URLs or AiDM arguments instead."
            if error.code == 0 else errors.getvalue().strip()
        )
        return GuiInputResult(argv=argv, error=message or "Invalid AiDM arguments.")

    return GuiInputResult(argv=argv, args=args)
