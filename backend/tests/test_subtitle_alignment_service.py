"""Focused tests for minimal subtitle/audio alignment."""

from __future__ import annotations

import unittest

from backend.app.models import SubtitleSegment
from backend.app.subtitle_alignment_service import (
    align_external_subtitles_to_reference,
)


def build_segment(
    *,
    segment_id: str,
    start: int,
    end: int,
    source_text: str,
) -> SubtitleSegment:
    return SubtitleSegment(
        id=segment_id,
        start=start,
        end=end,
        sourceText=source_text,
        translatedText="",
        sourceLanguage="en",
        targetLanguage="zh-CN",
    )


class SubtitleAlignmentServiceTests(unittest.TestCase):
    def test_matches_single_asr_segment(self) -> None:
        subtitle_segments = [
            build_segment(
                segment_id="seg-001",
                start=1000,
                end=2200,
                source_text="Hello, everyone.",
            )
        ]
        reference_segments = [
            build_segment(
                segment_id="asr-001",
                start=4000,
                end=5200,
                source_text="hello everyone",
            )
        ]

        result = align_external_subtitles_to_reference(
            subtitle_segments=subtitle_segments,
            reference_segments=reference_segments,
        )

        self.assertEqual(result.segments[0].start, 4000)
        self.assertEqual(result.segments[0].end, 5200)
        self.assertEqual(result.segments[0].sourceText, "Hello, everyone.")
        self.assertEqual(result.diagnostics.inputCueCount, 1)
        self.assertEqual(result.diagnostics.matchedCueCount, 1)
        self.assertEqual(result.diagnostics.fallbackCueCount, 0)
        self.assertEqual(result.diagnostics.matchedWithSingleAsrCount, 1)
        self.assertEqual(result.diagnostics.matchedWithMultiAsrCount, 0)

    def test_matches_two_contiguous_asr_segments(self) -> None:
        subtitle_segments = [
            build_segment(
                segment_id="seg-001",
                start=1000,
                end=3200,
                source_text="Hello everyone welcome back.",
            )
        ]
        reference_segments = [
            build_segment(
                segment_id="asr-001",
                start=0,
                end=900,
                source_text="Hello everyone",
            ),
            build_segment(
                segment_id="asr-002",
                start=900,
                end=1900,
                source_text="welcome back",
            ),
            build_segment(
                segment_id="asr-003",
                start=1900,
                end=2800,
                source_text="next sentence",
            ),
        ]

        result = align_external_subtitles_to_reference(
            subtitle_segments=subtitle_segments,
            reference_segments=reference_segments,
        )

        self.assertEqual(result.segments[0].start, 0)
        self.assertEqual(result.segments[0].end, 1900)
        self.assertEqual(result.diagnostics.matchedCueCount, 1)
        self.assertEqual(result.diagnostics.fallbackCueCount, 0)
        self.assertEqual(result.diagnostics.matchedWithSingleAsrCount, 0)
        self.assertEqual(result.diagnostics.matchedWithMultiAsrCount, 1)

    def test_falls_back_when_text_is_not_similar_enough(self) -> None:
        subtitle_segments = [
            build_segment(
                segment_id="seg-001",
                start=1000,
                end=2000,
                source_text="This is a very different sentence.",
            )
        ]
        reference_segments = [
            build_segment(
                segment_id="asr-001",
                start=0,
                end=900,
                source_text="Hello there",
            ),
            build_segment(
                segment_id="asr-002",
                start=900,
                end=1800,
                source_text="general kenobi",
            ),
        ]

        result = align_external_subtitles_to_reference(
            subtitle_segments=subtitle_segments,
            reference_segments=reference_segments,
        )

        self.assertEqual(result.segments[0].start, 1000)
        self.assertEqual(result.segments[0].end, 2000)
        self.assertEqual(result.diagnostics.matchedCueCount, 0)
        self.assertEqual(result.diagnostics.fallbackCueCount, 1)
        self.assertEqual(result.diagnostics.matchedWithSingleAsrCount, 0)
        self.assertEqual(result.diagnostics.matchedWithMultiAsrCount, 0)


if __name__ == "__main__":
    unittest.main()
