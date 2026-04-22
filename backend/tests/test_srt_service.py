"""Basic tests for the SRT parsing and export module."""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path

from backend.app.models import SubtitleSegment
from backend.app.srt_service import (
    SrtParseError,
    generate_srt,
    parse_srt,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class SrtServiceTests(unittest.TestCase):
    def test_parse_srt_returns_segments_in_shared_shape(self) -> None:
        file_path = FIXTURE_DIR / "numbering-disorder.srt"

        segments = parse_srt(
            file_path=file_path,
            source_language="en",
            target_language="zh-CN",
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].id, "seg-001")
        self.assertEqual(segments[0].start, 1000)
        self.assertEqual(segments[0].end, 3000)
        self.assertEqual(segments[0].sourceText, "Hello, everyone.")
        self.assertEqual(segments[0].translatedText, "")
        self.assertEqual(segments[0].sourceLanguage, "en")
        self.assertEqual(segments[0].targetLanguage, "zh-CN")
        self.assertEqual(segments[1].id, "seg-002")
        self.assertEqual(segments[1].sourceText, "Welcome\nto LinguaSub.")

    def test_parse_srt_raises_for_invalid_time_range(self) -> None:
        file_path = FIXTURE_DIR / "invalid-time.srt"

        with self.assertRaises(SrtParseError):
            parse_srt(file_path)

    def test_generate_srt_writes_bilingual_output(self) -> None:
        segments = [
            SubtitleSegment(
                id="seg-001",
                start=1000,
                end=3000,
                sourceText="Hello,\nworld.",
                translatedText="你好，世界。",
                sourceLanguage="en",
                targetLanguage="zh-CN",
            ),
            SubtitleSegment(
                id="seg-002",
                start=3500,
                end=5000,
                sourceText="Welcome to LinguaSub.",
                translatedText="欢迎使用 LinguaSub。",
                sourceLanguage="en",
                targetLanguage="zh-CN",
            ),
        ]

        content = generate_srt(segments, bilingual=True)

        expected = textwrap.dedent(
            """\
            1
            00:00:01,000 --> 00:00:03,000
            Hello, world.
            你好，世界。

            2
            00:00:03,500 --> 00:00:05,000
            Welcome to LinguaSub.
            欢迎使用 LinguaSub。
            """
        )
        self.assertEqual(content, expected)

    def test_generate_srt_single_mode_prefers_translated_text(self) -> None:
        segments = [
            SubtitleSegment(
                id="seg-003",
                start=0,
                end=1200,
                sourceText="Good morning.",
                translatedText="早上好。",
                sourceLanguage="en",
                targetLanguage="zh-CN",
            )
        ]

        content = generate_srt(segments, bilingual=False)

        self.assertIn("早上好。", content)
        self.assertNotIn("Good morning.", content)


if __name__ == "__main__":
    unittest.main()
