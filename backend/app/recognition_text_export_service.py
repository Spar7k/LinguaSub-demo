"""Plain TXT export for recognition source text."""

from __future__ import annotations

import math
from typing import Iterable

from .models import SubtitleSegment


class RecognitionTextExportError(ValueError):
    """Raised when recognition text cannot be exported safely."""


def _format_recognition_timestamp(value_ms: object) -> str:
    if not isinstance(value_ms, (int, float)) or not math.isfinite(value_ms):
        raise RecognitionTextExportError(
            "Recognition text export requires valid timestamps."
        )

    normalized = int(round(float(value_ms)))
    if normalized < 0:
        raise RecognitionTextExportError(
            "Recognition text export timestamps must not be negative."
        )

    total_seconds, milliseconds = divmod(normalized, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _normalize_source_text(text: str) -> str:
    return str(text).replace("\r\n", "\n").replace("\r", "\n").strip()


def generate_recognition_text(segments: Iterable[SubtitleSegment]) -> str:
    """Generate TXT content from subtitle recognition source text only."""

    segment_list = list(segments)
    if not segment_list:
        return ""

    if not any(segment.sourceText.strip() for segment in segment_list):
        raise RecognitionTextExportError(
            "No recognition text available. Please transcribe a video first."
        )

    blocks: list[str] = []
    for segment in segment_list:
        if segment.end < segment.start:
            raise RecognitionTextExportError(
                f"Subtitle segment '{segment.id}' ends before it starts."
            )

        start = _format_recognition_timestamp(segment.start)
        end = _format_recognition_timestamp(segment.end)
        source_text = _normalize_source_text(segment.sourceText)
        blocks.append(f"[{start} - {end}]\n{source_text}")

    return "\n\n".join(blocks) + "\n"


def generateRecognitionText(segments: Iterable[SubtitleSegment]) -> str:
    return generate_recognition_text(segments=segments)
