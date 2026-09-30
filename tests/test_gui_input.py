import contextlib
import io
import shlex
import unittest
from unittest.mock import patch

import aidm
from gui_input import normalize_gui_input, validate_gui_input


class GuiInputTests(unittest.TestCase):
    def setUp(self):
        # Parsing must never reach routing, the network, or external commands.
        for target in (
            "aidm.run_from_args",
            "urllib.request.urlopen",
            "socket.socket.connect",
            "subprocess.run",
            "subprocess.Popen",
        ):
            guard = patch(target, side_effect=AssertionError(f"Unexpected {target}"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_plain_urls_and_nargs_contract(self):
        first = "https://example.com/a.zip"
        second = "https://example.com/b.zip"
        cases = [
            (first, [first]),
            ("https://www.youtube.com/watch?v=abcdefghijk", [
                "https://www.youtube.com/watch?v=abcdefghijk",
            ]),
            (f"{first} {second}", [first, second]),
            (f"{first}\n{second}", [first, second]),
            (f"{first}\r\n{second}", [first, second]),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(normalize_gui_input(text), expected)
                result = validate_gui_input(text)
                self.assertIsNone(result.error)
                self.assertEqual(result.args.urls, expected)
                self.assertEqual(vars(result.args), vars(aidm.parse_args(expected)))

    def test_full_inspector_fragment(self):
        media = "https://cdn.example/master.m3u8?token=a%2Fb&expires=123&sig=x=y#part"
        text = (
            "--user-agent 'Mozilla/5.0 Example Browser' "
            "--referer 'https://example.com/player?a=1&b=2' "
            "--subtitle 'https://cdn.example/sub.vtt?key=a%20b&lang=en' "
            "--title 'Example Movie' '" + media + "'"
        )
        result = validate_gui_input(text)
        self.assertIsNone(result.error)
        self.assertEqual(result.args.user_agent, "Mozilla/5.0 Example Browser")
        self.assertEqual(result.args.referer, "https://example.com/player?a=1&b=2")
        self.assertEqual(result.args.subtitle, ["https://cdn.example/sub.vtt?key=a%20b&lang=en"])
        self.assertEqual(result.args.title, "Example Movie")
        self.assertEqual(result.args.urls, [media])

    def test_no_subtitle_and_posix_apostrophe(self):
        text = "--title 'John'\"'\"'s Movie' https://cdn.example/master.m3u8"
        result = validate_gui_input(text)
        self.assertIsNone(result.error)
        self.assertEqual(result.args.title, "John's Movie")
        self.assertEqual(result.args.subtitle, [])

    def test_subtitle_order_and_duplicates(self):
        subtitles = ["https://cdn.example/en.vtt", "https://cdn.example/ur.vtt", "https://cdn.example/en.vtt"]
        argv = []
        for subtitle in subtitles:
            argv.extend(["--subtitle", subtitle])
        argv.append("https://cdn.example/master.m3u8")
        result = validate_gui_input(shlex.join(argv))
        self.assertEqual(result.argv, argv)
        self.assertEqual(result.args.subtitle, subtitles)

    def test_unquoted_signed_url_is_unchanged(self):
        url = "https://cdn.example/master.m3u8?token=a%2Fb&sig=x=y#part"
        self.assertEqual(normalize_gui_input(url), [url])
        self.assertEqual(validate_gui_input(url).args.urls, [url])

    def test_empty_skips_parser(self):
        with patch("gui_input.parse_args") as parser:
            for text in ["", " ", "\t\n\r "]:
                with self.subTest(text=text):
                    self.assertEqual(normalize_gui_input(text), [])
                    result = validate_gui_input(text)
                    self.assertEqual(result.argv, [])
                    self.assertIsNone(result.args)
                    self.assertIsNone(result.error)
            parser.assert_not_called()

    def test_malformed_quoting_skips_parser_and_recovers(self):
        for text in ["--title 'unfinished", '--title "unfinished', "https://example.com/\\"]:
            with self.subTest(text=text), patch("gui_input.parse_args") as parser:
                with self.assertRaises(ValueError):
                    normalize_gui_input(text)
                result = validate_gui_input(text)
                self.assertIsNone(result.args)
                self.assertTrue(result.error)
                parser.assert_not_called()
        self.assertIsNone(validate_gui_input("--title 'finished' https://example.com/a").error)

    def test_argparse_errors_and_help_are_captured(self):
        for text in ["--title", "--title Movie", "--unknown https://example.com/a", "--help"]:
            with self.subTest(text=text):
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    result = validate_gui_input(text)
                self.assertEqual(output.getvalue(), "")
                self.assertIsNone(result.args)
                self.assertTrue(result.error)

    def test_existing_parser_is_called_with_normalized_tokens(self):
        argv = ["--title", "A Movie", "https://example.com/a", "https://example.com/b"]
        with patch("gui_input.parse_args", wraps=aidm.parse_args) as parser:
            result = validate_gui_input(shlex.join(argv))
            parser.assert_called_once_with(argv)
        self.assertEqual(result.args.urls, argv[-2:])

    def test_shell_syntax_remains_literal_data(self):
        title = "$(touch should-not-exist); `id` $HOME *"
        result = validate_gui_input(shlex.join(["--title", title, "https://example.com/a"]))
        self.assertEqual(result.args.title, title)


if __name__ == "__main__":
    unittest.main()
