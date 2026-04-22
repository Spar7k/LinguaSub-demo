"""SRT parsing and export helpers for LinguaSub."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .models import LanguageCode, SubtitleSegment

DEFAULT_TARGET_LANGUAGE: LanguageCode = "zh-CN"
READ_ENCODINGS: tuple[str, ...] = (
    "utf-8-sig",
    "utf-16",
    "gb18030",
    "cp932",
    "euc-kr",
    "big5",
)

TIMESTAMP_PATTERN = re.compile(
    r"^(?P<hours>\d{2,}):(?P<minutes>\d{2}):(?P<seconds>\d{2}),(?P<milliseconds>\d{3})$"
)
TIME_RANGE_PATTERN = re.compile(
    r"^(?P<start>\d{2,}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2,}:\d{2}:\d{2},\d{3})$"
)


class SrtServiceError(ValueError):
    """Base error for SRT parsing and export."""


class SrtEncodingError(SrtServiceError):
    """Raised when the SRT file cannot be decoded safely."""


class SrtParseError(SrtServiceError):
    """Raised when the SRT structure or timestamps are invalid."""


class SrtGenerationError(SrtServiceError):
    """Raised when subtitle segments cannot be exported to SRT."""


def _read_srt_text(file_path: Path) -> str:
    if not file_path.exists():
        raise SrtServiceError(f"SRT file does not exist: {file_path}")

    if not file_path.is_file():
        raise SrtServiceError(f"SRT path is not a file: {file_path}")

    last_error: UnicodeDecodeError | None = None
    for encoding in READ_ENCODINGS:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    raise SrtEncodingError(
        f"Could not decode SRT file '{file_path.name}'. "
        f"Tried encodings: {', '.join(READ_ENCODINGS)}."
    ) from last_error


def _split_srt_blocks(text: str) -> list[list[str]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        if not line.strip():
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue

        current_block.append(line)

    if current_block:
        blocks.append(current_block)

    return blocks


def _parse_timestamp(timestamp: str, *, block_number: int) -> int:
    match = TIMESTAMP_PATTERN.fullmatch(timestamp.strip())
    if match is None:
        raise SrtParseError(
            f"Invalid timestamp in block {block_number}: '{timestamp}'."
        )

    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    milliseconds = int(match.group("milliseconds"))

    if minutes >= 60 or seconds >= 60:
        raise SrtParseError(
            f"Invalid timestamp value in block {block_number}: '{timestamp}'."
        )

    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + milliseconds


def _parse_time_range(time_line: str, *, block_number: int) -> tuple[int, int]:
    match = TIME_RANGE_PATTERN.fullmatch(time_line.strip())
    if match is None:
        raise SrtParseError(
            f"Invalid time range in block {block_number}: '{time_line}'."
        )

    start_ms = _parse_timestamp(match.group("start"), block_number=block_number)
    end_ms = _parse_timestamp(match.group("end"), block_number=block_number)
    if end_ms < start_ms:
        raise SrtParseError(
            f"End time is earlier than start time in block {block_number}."
        )

    return start_ms, end_ms


def _format_timestamp(value_ms: int) -> str:
    if value_ms < 0:
        raise SrtGenerationError("SRT timestamps must not be negative.")

    total_seconds, milliseconds = divmod(value_ms, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _normalize_export_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines)


def parse_srt(
    file_path: str | Path,
    source_language: LanguageCode = "auto",
    target_language: LanguageCode = DEFAULT_TARGET_LANGUAGE,
) -> list[SubtitleSegment]:
    """Parse an SRT file into the shared subtitle segment structure."""

    path = Path(file_path).expanduser().resolve()
    text = _read_srt_text(path)
    blocks = _split_srt_blocks(text)

    segments: list[SubtitleSegment] = []
    for block_number, lines in enumerate(blocks, start=1):
        if not lines:
            continue

        cleaned_lines = [line.lstrip("\ufeff").rstrip() for line in lines]
        time_line_index = 0

        if cleaned_lines[0].strip().isdigit():
            if len(cleaned_lines) == 1:
                continue
            time_line_index = 1

        time_line = cleaned_lines[time_line_index].strip()
        start_ms, end_ms = _parse_time_range(time_line, block_number=block_number)

        text_lines = [
            line.strip()
            for line in cleaned_lines[time_line_index + 1 :]
            if line.strip()
        ]
        if not text_lines:
            continue

        segments.append(
            SubtitleSegment(
                id=f"seg-{len(segments) + 1:03d}",
                start=start_ms,
                end=end_ms,
                sourceText="\n".join(text_lines),
                translatedText="",
                sourceLanguage=source_language,
                targetLanguage=target_language,
            )
        )

    return segments


def generate_srt(
    segments: Iterable[SubtitleSegment],
    bilingual: bool = True,
) -> str:
    """Generate SRT content from subtitle segments."""

    segment_list = list(segments)
    if not segment_list:
        return ""

    blocks: list[str] = []
    for index, segment in enumerate(segment_list, start=1):
        if segment.end < segment.start:
            raise SrtGenerationError(
                f"Subtitle segment '{segment.id}' ends before it starts."
            )

        source_text = _normalize_export_text(segment.sourceText)
        translated_text = _normalize_export_text(segment.translatedText)

        if bilingual:
            text_lines = [line for line in [source_text, translated_text] if line]
        else:
            single_line = translated_text or source_text
            text_lines = [single_line] if single_line else []

        if not text_lines:
            raise SrtGenerationError(
                f"Subtitle segment '{segment.id}' has no text to export."
            )

        block_lines = [
            str(index),
            f"{_format_timestamp(segment.start)} --> {_format_timestamp(segment.end)}",
            *text_lines,
        ]
        blocks.append("\n".join(block_lines))

    return "\n\n".join(blocks) + "\n"


def parseSrt(
    file_path: str | Path,
    source_language: LanguageCode = "auto",
    target_language: LanguageCode = DEFAULT_TARGET_LANGUAGE,
) -> list[SubtitleSegment]:
    return parse_srt(
        file_path=file_path,
        source_language=source_language,
        target_language=target_language,
    )


def generateSrt(segments: Iterable[SubtitleSegment], bilingual: bool = True) -> str:
    return generate_srt(segments=segments, bilingual=bilingual)
