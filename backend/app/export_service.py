"""Subtitle export service for writing SRT and Word files to disk."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .models import JsonModel, SubtitleSegment
from .srt_service import generate_srt
from .word_export_service import (
    WORD_EXPORT_MODE_BILINGUAL_TABLE,
    WORD_EXPORT_MODE_TRANSCRIPT,
    WordExportError,
    generate_word_document,
    validate_word_export_mode,
)

ExportFormat = Literal["srt", "word"]
WordExportMode = Literal["bilingualTable", "transcript"]

DEFAULT_EXPORT_STEM = "linguasub-subtitles"
DEFAULT_EXPORT_ENCODING = "utf-8-sig"
INVALID_FILE_NAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
REPEATED_UNDERSCORE_PATTERN = re.compile(r"_+")
TRAILING_DOTS_AND_SPACES_RE = re.compile(r"[. ]+$")
SUPPORTED_EXPORT_FORMATS = {"srt", "word"}
EXPORT_EXTENSION_MAP: dict[ExportFormat, str] = {
    "srt": ".srt",
    "word": ".docx",
}


class ExportServiceError(RuntimeError):
    """Base error for subtitle export problems."""


class EmptySubtitleExportError(ExportServiceError):
    """Raised when there are no subtitle segments to export."""


class MissingTranslationExportError(ExportServiceError):
    """Raised when bilingual export is requested without translations."""


class InvalidExportPathError(ExportServiceError):
    """Raised when the export file name or destination is unsafe."""


class ExportWriteError(ExportServiceError):
    """Raised when LinguaSub cannot write the export file."""


@dataclass(slots=True)
class ExportResult(JsonModel):
    path: str
    directory: str
    fileName: str
    format: ExportFormat
    bilingual: bool
    wordMode: WordExportMode | None
    count: int
    conflictResolved: bool = False
    sanitizedFileName: bool = False


def _normalize_export_format(export_format: str | None) -> ExportFormat:
    normalized = (export_format or "srt").strip().lower()
    if normalized in SUPPORTED_EXPORT_FORMATS:
        return normalized  # type: ignore[return-value]

    supported = ", ".join(sorted(SUPPORTED_EXPORT_FORMATS))
    raise ExportServiceError(
        f"Unsupported export format '{export_format}'. Use one of: {supported}."
    )


def _clean_file_name_stem(file_name: str) -> tuple[str, bool]:
    cleaned = INVALID_FILE_NAME_PATTERN.sub("_", file_name.strip())
    cleaned = REPEATED_UNDERSCORE_PATTERN.sub("_", cleaned)
    cleaned = TRAILING_DOTS_AND_SPACES_RE.sub("", cleaned)
    return cleaned, cleaned != file_name.strip()


def _normalize_file_name(file_name: str, *, export_format: ExportFormat) -> tuple[str, bool]:
    cleaned = file_name.strip()
    if not cleaned:
        raise InvalidExportPathError("Export file name is required.")
    if Path(cleaned).name != cleaned:
        raise InvalidExportPathError("File name must not include folder separators.")
    if cleaned in {".", ".."}:
        raise InvalidExportPathError("File name is not valid.")

    expected_extension = EXPORT_EXTENSION_MAP[export_format]
    lower_cleaned = cleaned.lower()
    was_sanitized = False
    if lower_cleaned.endswith(expected_extension):
        cleaned, was_sanitized = _clean_file_name_stem(
            cleaned[: -len(expected_extension)]
        )
        if not cleaned:
            raise InvalidExportPathError("File name is not valid after removing unsupported characters.")
        return f"{cleaned}{expected_extension}", was_sanitized

    for known_extension in EXPORT_EXTENSION_MAP.values():
        if lower_cleaned.endswith(known_extension):
            cleaned = cleaned[: -len(known_extension)]
            break

    cleaned, was_sanitized = _clean_file_name_stem(cleaned)
    if not cleaned:
        raise InvalidExportPathError("File name is not valid after removing unsupported characters.")
    return f"{cleaned}{expected_extension}", was_sanitized


def _build_available_export_path(export_path: Path) -> tuple[Path, bool]:
    if not export_path.exists():
        return export_path, False

    stem = export_path.stem
    suffix = export_path.suffix
    for index in range(1, 1000):
        candidate = export_path.with_name(f"{stem}({index}){suffix}")
        if not candidate.exists():
            return candidate, True

    raise ExportWriteError(
        "LinguaSub could not find an available export file name. Please rename the export file and try again."
    )


def _build_default_file_name(
    source_file_path: str | Path | None,
    *,
    export_format: ExportFormat,
    bilingual: bool,
    word_mode: WordExportMode,
) -> str:
    stem = DEFAULT_EXPORT_STEM
    if source_file_path:
        stem = Path(source_file_path).stem or DEFAULT_EXPORT_STEM

    if export_format == "word":
        if word_mode == WORD_EXPORT_MODE_BILINGUAL_TABLE:
            return f"{stem}_bilingual.docx"
        if word_mode == WORD_EXPORT_MODE_TRANSCRIPT:
            return f"{stem}_transcript.docx"
        return f"{stem}.docx"

    suffix = "bilingual" if bilingual else "single"
    return f"{stem}.{suffix}.srt"


def _resolve_export_path(
    source_file_path: str | Path | None,
    *,
    export_format: ExportFormat,
    bilingual: bool,
    word_mode: WordExportMode,
    file_name: str | None,
) -> Path:
    sanitized_file_name = False
    if source_file_path:
        source_path = Path(source_file_path).expanduser().resolve()
        target_dir = source_path.parent
    else:
        source_path = None
        target_dir = Path.cwd()

    target_dir.mkdir(parents=True, exist_ok=True)
    resolved_name = (
        _normalize_file_name(file_name, export_format=export_format)[0]
        if file_name and file_name.strip()
        else _build_default_file_name(
            source_file_path,
            export_format=export_format,
            bilingual=bilingual,
            word_mode=word_mode,
        )
    )

    export_path = (target_dir / resolved_name).resolve()
    if source_path and export_path == source_path:
        raise InvalidExportPathError(
            "Export would overwrite the imported source file. Choose a different file name."
        )

    return export_path


def _resolve_export_target(
    source_file_path: str | Path | None,
    *,
    export_format: ExportFormat,
    bilingual: bool,
    word_mode: WordExportMode,
    file_name: str | None,
) -> tuple[Path, bool, bool]:
    if file_name and file_name.strip():
        normalized_file_name, sanitized_file_name = _normalize_file_name(
            file_name,
            export_format=export_format,
        )
        base_path = _resolve_export_path(
            source_file_path=source_file_path,
            export_format=export_format,
            bilingual=bilingual,
            word_mode=word_mode,
            file_name=normalized_file_name,
        )
    else:
        sanitized_file_name = False
        base_path = _resolve_export_path(
            source_file_path=source_file_path,
            export_format=export_format,
            bilingual=bilingual,
            word_mode=word_mode,
            file_name=None,
        )

    available_path, conflict_resolved = _build_available_export_path(base_path)
    return available_path, conflict_resolved, sanitized_file_name


def _validate_segments(
    segments: list[SubtitleSegment],
    *,
    export_format: ExportFormat,
    bilingual: bool,
) -> None:
    if not segments:
        raise EmptySubtitleExportError("There are no subtitle segments to export.")

    if export_format == "srt" and bilingual:
        missing_translation_ids = [
            segment.id for segment in segments if not segment.translatedText.strip()
        ]
        if missing_translation_ids:
            preview_ids = ", ".join(missing_translation_ids[:3])
            if len(missing_translation_ids) > 3:
                preview_ids = f"{preview_ids}, ..."
            raise MissingTranslationExportError(
                "Bilingual export requires translated text for every subtitle segment. "
                f"Missing translations: {preview_ids}."
            )


def export_subtitles(
    segments: list[SubtitleSegment],
    *,
    export_format: str = "srt",
    bilingual: bool = True,
    word_mode: str = WORD_EXPORT_MODE_BILINGUAL_TABLE,
    source_file_path: str | Path | None = None,
    file_name: str | None = None,
) -> ExportResult:
    """Generate the selected export format and save it to disk."""

    normalized_format = _normalize_export_format(export_format)
    normalized_word_mode = validate_word_export_mode(word_mode)
    _validate_segments(segments, export_format=normalized_format, bilingual=bilingual)
    export_path, conflict_resolved, sanitized_file_name = _resolve_export_target(
        source_file_path=source_file_path,
        export_format=normalized_format,
        bilingual=bilingual,
        word_mode=normalized_word_mode,
        file_name=file_name,
    )

    try:
        if normalized_format == "word":
            content = generate_word_document(segments, mode=normalized_word_mode)
            export_path.write_bytes(content)
        else:
            content = generate_srt(segments, bilingual=bilingual)
            export_path.write_text(content, encoding=DEFAULT_EXPORT_ENCODING)
    except WordExportError as exc:
        raise ExportWriteError(str(exc)) from exc
    except OSError as exc:
        raw_error = exc.strerror or str(exc)
        lowered = raw_error.lower()
        if getattr(exc, "winerror", None) == 32:
            raise ExportWriteError(
                f"Could not write export file '{export_path.name}'. The file is currently open in another program. Close the file and try again."
            ) from exc
        if getattr(exc, "winerror", None) == 5 or "permission denied" in lowered:
            raise ExportWriteError(
                f"Could not write export file '{export_path.name}'. LinguaSub does not have permission to write to the target folder."
            ) from exc
        raise ExportWriteError(
            f"Could not write export file '{export_path.name}'. {raw_error}"
        ) from exc

    return ExportResult(
        path=str(export_path),
        directory=str(export_path.parent),
        fileName=export_path.name,
        format=normalized_format,
        bilingual=bilingual,
        wordMode=normalized_word_mode if normalized_format == "word" else None,
        count=len(segments),
        conflictResolved=conflict_resolved,
        sanitizedFileName=sanitized_file_name,
    )


def export_srt(
    segments: list[SubtitleSegment],
    *,
    bilingual: bool = True,
    source_file_path: str | Path | None = None,
    file_name: str | None = None,
) -> ExportResult:
    return export_subtitles(
        segments=segments,
        export_format="srt",
        bilingual=bilingual,
        word_mode=WORD_EXPORT_MODE_BILINGUAL_TABLE,
        source_file_path=source_file_path,
        file_name=file_name,
    )


def export_word(
    segments: list[SubtitleSegment],
    *,
    word_mode: str = WORD_EXPORT_MODE_BILINGUAL_TABLE,
    source_file_path: str | Path | None = None,
    file_name: str | None = None,
) -> ExportResult:
    return export_subtitles(
        segments=segments,
        export_format="word",
        bilingual=True,
        word_mode=word_mode,
        source_file_path=source_file_path,
        file_name=file_name,
    )


def exportSrt(
    segments: list[SubtitleSegment],
    *,
    bilingual: bool = True,
    source_file_path: str | Path | None = None,
    file_name: str | None = None,
) -> ExportResult:
    return export_srt(
        segments=segments,
        bilingual=bilingual,
        source_file_path=source_file_path,
        file_name=file_name,
    )


def exportWord(
    segments: list[SubtitleSegment],
    *,
    word_mode: str = WORD_EXPORT_MODE_BILINGUAL_TABLE,
    source_file_path: str | Path | None = None,
    file_name: str | None = None,
) -> ExportResult:
    return export_word(
        segments=segments,
        word_mode=word_mode,
        source_file_path=source_file_path,
        file_name=file_name,
    )
