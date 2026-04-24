"""Burn subtitle segments into a source video with FFmpeg."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .import_service import detect_file_type
from .models import JsonModel, SubtitleSegment
from .speech_runtime_service import resolve_ffmpeg_binary, resolve_ffprobe_binary

VideoBurnMode = Literal["translated", "bilingual", "source"]
VideoBurnProfile = Literal[
    "portrait_short",
    "portrait_long",
    "landscape_short",
    "landscape_long",
]

ASS_FILE_NAME = "subtitles.ass"
DEFAULT_ASS_FONT = "Microsoft YaHei"
SUPPORTED_VIDEO_BURN_MODES: set[str] = {"translated", "bilingual", "source"}
DEFAULT_VIDEO_BURN_PROFILE: VideoBurnProfile = "landscape_long"
SHORT_VIDEO_THRESHOLD_SECONDS = 180.0

LOGGER = logging.getLogger(__name__)


class VideoBurnExportServiceError(RuntimeError):
    """Raised when burned-in video export cannot be completed."""


@dataclass(slots=True)
class VideoBurnExportResult(JsonModel):
    outputPath: str
    directory: str
    fileName: str
    mode: VideoBurnMode
    count: int
    status: str = "done"
    message: str = "Video export completed."


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    rotation: int = 0

    @property
    def display_width(self) -> int | None:
        if self.width is None or self.height is None:
            return self.width
        if abs(self.rotation) % 180 == 90:
            return self.height
        return self.width

    @property
    def display_height(self) -> int | None:
        if self.width is None or self.height is None:
            return self.height
        if abs(self.rotation) % 180 == 90:
            return self.width
        return self.height


@dataclass(frozen=True, slots=True)
class AssStyleProfile:
    name: VideoBurnProfile
    play_res_x: int
    play_res_y: int
    font_size: int
    source_font_size: int
    margin_v: int
    margin_l: int = 64
    margin_r: int = 64
    outline: int = 2
    shadow: int = 0


ASS_STYLE_PROFILES: dict[VideoBurnProfile, AssStyleProfile] = {
    "portrait_short": AssStyleProfile(
        name="portrait_short",
        play_res_x=1080,
        play_res_y=1920,
        font_size=36,
        source_font_size=30,
        margin_v=300,
        margin_l=56,
        margin_r=56,
    ),
    "portrait_long": AssStyleProfile(
        name="portrait_long",
        play_res_x=1080,
        play_res_y=1920,
        font_size=38,
        source_font_size=32,
        margin_v=220,
        margin_l=60,
        margin_r=60,
    ),
    "landscape_short": AssStyleProfile(
        name="landscape_short",
        play_res_x=1920,
        play_res_y=1080,
        font_size=44,
        source_font_size=36,
        margin_v=96,
    ),
    "landscape_long": AssStyleProfile(
        name="landscape_long",
        play_res_x=1920,
        play_res_y=1080,
        font_size=42,
        source_font_size=34,
        margin_v=64,
    ),
}


def _normalize_video_path(raw_path: str) -> Path:
    cleaned = str(raw_path or "").strip().strip('"').strip("'")
    if not cleaned:
        raise VideoBurnExportServiceError("videoPath is required.")

    path = Path(cleaned).expanduser().resolve()
    if not path.exists():
        raise VideoBurnExportServiceError(f"Source video does not exist: {path}")
    if not path.is_file():
        raise VideoBurnExportServiceError(f"Source video path is not a file: {path}")
    try:
        media_type = detect_file_type(path)
    except Exception as exc:
        raise VideoBurnExportServiceError(str(exc)) from exc
    if media_type != "video":
        raise VideoBurnExportServiceError("videoPath must point to a supported video file.")
    return path


def _normalize_output_path(raw_path: str) -> Path:
    cleaned = str(raw_path or "").strip().strip('"').strip("'")
    if not cleaned:
        raise VideoBurnExportServiceError("outputPath is required.")

    path = Path(cleaned).expanduser().resolve()
    if path.suffix.lower() != ".mp4":
        raise VideoBurnExportServiceError("outputPath must end with .mp4 for the MVP video export.")
    if path.exists() and path.is_dir():
        raise VideoBurnExportServiceError("outputPath must be a file path, not a folder.")
    if not path.parent.exists() or not path.parent.is_dir():
        raise VideoBurnExportServiceError(f"Output folder does not exist: {path.parent}")
    return path


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _normalize_mode(mode: str | None) -> VideoBurnMode:
    normalized = (mode or "bilingual").strip().lower()
    if normalized in SUPPORTED_VIDEO_BURN_MODES:
        return normalized  # type: ignore[return-value]

    supported = ", ".join(sorted(SUPPORTED_VIDEO_BURN_MODES))
    raise VideoBurnExportServiceError(
        f"Unsupported video subtitle burn mode '{mode}'. Use one of: {supported}."
    )


def _safe_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_rotation(stream: dict[str, object]) -> int:
    tags = stream.get("tags")
    if isinstance(tags, dict):
        rotation = _safe_int(tags.get("rotate"))
        if rotation is not None:
            return rotation

    side_data_list = stream.get("side_data_list")
    if isinstance(side_data_list, list):
        for item in side_data_list:
            if not isinstance(item, dict):
                continue
            rotation = _safe_int(item.get("rotation"))
            if rotation is not None:
                return rotation

    return 0


def _probe_video_metadata(ffprobe_binary: Path, video_path: Path) -> VideoMetadata:
    command = [
        str(ffprobe_binary),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,duration:stream_tags=rotate:stream_side_data=rotation:format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", [])
    stream = streams[0] if isinstance(streams, list) and streams else {}
    if not isinstance(stream, dict):
        stream = {}
    format_payload = payload.get("format", {})
    if not isinstance(format_payload, dict):
        format_payload = {}

    duration_seconds = _safe_float(format_payload.get("duration")) or _safe_float(
        stream.get("duration")
    )
    return VideoMetadata(
        width=_safe_int(stream.get("width")),
        height=_safe_int(stream.get("height")),
        duration_seconds=duration_seconds,
        rotation=_extract_rotation(stream),
    )


def _max_segment_end_seconds(segments: list[SubtitleSegment]) -> float | None:
    max_end = max(
        (segment.end for segment in segments if isinstance(segment.end, (int, float))),
        default=0,
    )
    return max_end / 1000 if max_end > 0 else None


def classify_video_burn_profile(
    metadata: VideoMetadata,
    segments: list[SubtitleSegment],
) -> VideoBurnProfile:
    display_width = metadata.display_width
    display_height = metadata.display_height
    orientation = (
        "portrait"
        if display_width is not None
        and display_height is not None
        and display_height > display_width * 1.1
        else "landscape"
    )
    duration_seconds = metadata.duration_seconds or _max_segment_end_seconds(segments)
    length = (
        "short"
        if duration_seconds is not None
        and duration_seconds <= SHORT_VIDEO_THRESHOLD_SECONDS
        else "long"
    )
    return f"{orientation}_{length}"  # type: ignore[return-value]


def resolve_video_burn_profile(
    video_path: Path,
    segments: list[SubtitleSegment],
) -> VideoBurnProfile:
    ffprobe_binary = resolve_ffprobe_binary()
    if ffprobe_binary is None:
        LOGGER.info(
            "FFprobe is not available; falling back to video burn profile '%s'.",
            DEFAULT_VIDEO_BURN_PROFILE,
        )
        return DEFAULT_VIDEO_BURN_PROFILE

    try:
        metadata = _probe_video_metadata(ffprobe_binary, video_path)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        LOGGER.info(
            "Could not probe video metadata for '%s'; falling back to video burn profile '%s'. Error: %s",
            video_path.name,
            DEFAULT_VIDEO_BURN_PROFILE,
            exc,
        )
        return DEFAULT_VIDEO_BURN_PROFILE

    profile = classify_video_burn_profile(metadata, segments)
    LOGGER.info(
        "Resolved video burn profile '%s' for '%s' width=%s height=%s display=%sx%s duration=%s rotation=%s.",
        profile,
        video_path.name,
        metadata.width,
        metadata.height,
        metadata.display_width,
        metadata.display_height,
        metadata.duration_seconds,
        metadata.rotation,
    )
    return profile


def _resolve_ass_style_profile(profile: VideoBurnProfile | str | None) -> AssStyleProfile:
    if profile in ASS_STYLE_PROFILES:
        return ASS_STYLE_PROFILES[profile]  # type: ignore[index]
    return ASS_STYLE_PROFILES[DEFAULT_VIDEO_BURN_PROFILE]


def _format_ass_timestamp(value_ms: int) -> str:
    if value_ms < 0:
        raise VideoBurnExportServiceError("Subtitle timestamps must not be negative.")

    centiseconds = int(round(value_ms / 10))
    total_seconds, centisecond = divmod(centiseconds, 100)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centisecond:02d}"


def _normalize_text_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _escape_ass_text_line(line: str) -> str:
    return (
        line.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def _format_ass_text_lines(lines: list[str], *, font_size: int | None = None) -> list[str]:
    escaped_lines = [_escape_ass_text_line(line) for line in lines if line.strip()]
    if font_size is None:
        return escaped_lines
    return [rf"{{\fs{font_size}}}{line}" for line in escaped_lines]


def _build_ass_text(
    segment: SubtitleSegment,
    mode: VideoBurnMode,
    style: AssStyleProfile,
) -> str:
    source_lines = _normalize_text_lines(segment.sourceText)
    translated_lines = _normalize_text_lines(segment.translatedText)

    if mode == "source":
        text_lines = _format_ass_text_lines(source_lines)
    elif mode == "translated":
        text_lines = _format_ass_text_lines(translated_lines or source_lines)
    elif translated_lines:
        # MVP bilingual layout: keep both languages in one ASS event but make
        # the source line secondary with a smaller override font size.
        text_lines = [
            *_format_ass_text_lines(source_lines, font_size=style.source_font_size),
            *_format_ass_text_lines(translated_lines, font_size=style.font_size),
        ]
    else:
        text_lines = _format_ass_text_lines(source_lines)

    return r"\N".join(text_lines)


def _build_ass_dialogue_line(
    segment: SubtitleSegment,
    mode: VideoBurnMode,
    style: AssStyleProfile,
) -> str:
    if segment.end <= segment.start:
        raise VideoBurnExportServiceError(
            f"Subtitle segment '{segment.id}' must end after it starts."
        )

    text = _build_ass_text(segment, mode, style)
    if not text:
        raise VideoBurnExportServiceError(
            f"Subtitle segment '{segment.id}' has no text to burn into the video."
        )

    return (
        "Dialogue: 0,"
        f"{_format_ass_timestamp(segment.start)},"
        f"{_format_ass_timestamp(segment.end)},"
        "Default,,0,0,0,,"
        f"{text}"
    )


def generate_ass_content(
    segments: list[SubtitleSegment],
    *,
    mode: str = "bilingual",
    profile: VideoBurnProfile | str | None = DEFAULT_VIDEO_BURN_PROFILE,
) -> str:
    """Generate a minimal ASS subtitle file for FFmpeg subtitles filter."""

    if not segments:
        raise VideoBurnExportServiceError("There are no subtitle segments to burn.")

    normalized_mode = _normalize_mode(mode)
    style = _resolve_ass_style_profile(profile)
    dialogue_lines = [
        _build_ass_dialogue_line(segment, normalized_mode, style) for segment in segments
    ]

    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {style.play_res_x}",
            f"PlayResY: {style.play_res_y}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{DEFAULT_ASS_FONT},{style.font_size},&H00FFFFFF,&H00FFFFFF,"
            "&H00000000,&H80000000,0,0,0,0,100,100,0,0,"
            f"1,{style.outline},{style.shadow},2,{style.margin_l},{style.margin_r},{style.margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *dialogue_lines,
            "",
        ]
    )


def build_ffmpeg_burn_command(
    ffmpeg_binary: Path,
    video_path: Path,
    output_path: Path,
    *,
    ass_file_name: str = ASS_FILE_NAME,
) -> list[str]:
    return [
        str(ffmpeg_binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        f"subtitles=filename={ass_file_name}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _run_ffmpeg_command(command: list[str], *, cwd: Path) -> None:
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
    )


@contextmanager
def _create_temporary_ass_directory(parent: Path) -> Iterator[Path]:
    temp_dir = parent / f".linguasub-burn-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=False, exist_ok=False)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def burn_video_subtitles(
    *,
    video_path: str,
    output_path: str,
    segments: list[SubtitleSegment],
    mode: str = "bilingual",
) -> VideoBurnExportResult:
    source_video_path = _normalize_video_path(video_path)
    target_output_path = _normalize_output_path(output_path)
    normalized_mode = _normalize_mode(mode)

    if _same_path(source_video_path, target_output_path):
        raise VideoBurnExportServiceError("outputPath must not overwrite the source video.")

    ffmpeg_binary = resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        raise VideoBurnExportServiceError(
            "FFmpeg is not available. Reinstall LinguaSub with bundled ffmpeg.exe or configure a local FFmpeg binary."
        )

    profile = resolve_video_burn_profile(source_video_path, segments)
    ass_content = generate_ass_content(
        segments,
        mode=normalized_mode,
        profile=profile,
    )

    with _create_temporary_ass_directory(target_output_path.parent) as temp_dir:
        ass_path = temp_dir / ASS_FILE_NAME
        ass_path.write_text(ass_content, encoding="utf-8-sig")

        command = build_ffmpeg_burn_command(
            ffmpeg_binary=ffmpeg_binary,
            video_path=source_video_path,
            output_path=target_output_path,
            ass_file_name=ASS_FILE_NAME,
        )

        try:
            _run_ffmpeg_command(command, cwd=temp_dir)
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "").strip() or "Unknown FFmpeg error."
            raise VideoBurnExportServiceError(
                f"FFmpeg could not export the burned-in subtitle video. {message}"
            ) from exc

    if not target_output_path.exists():
        raise VideoBurnExportServiceError(
            f"FFmpeg finished but the output video was not created: {target_output_path}"
        )

    return VideoBurnExportResult(
        outputPath=str(target_output_path),
        directory=str(target_output_path.parent),
        fileName=target_output_path.name,
        mode=normalized_mode,
        count=len(segments),
        message="Video with burned-in subtitles exported successfully.",
    )
