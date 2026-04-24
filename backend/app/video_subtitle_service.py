"""Video subtitle orchestration for the MVP video-subtitle module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .import_service import UnsupportedFileTypeError, create_project_file
from .models import (
    AppConfig,
    JsonModel,
    LanguageCode,
    OutputMode,
    ProjectFile,
    ProviderName,
    SubtitleSegment,
)
from .srt_service import SrtServiceError, parse_srt
from .subtitle_alignment_service import (
    SubtitleAlignmentDiagnostics,
    SubtitleAlignmentServiceError,
    align_external_subtitles_to_reference,
)
from .transcription_service import TranscriptionDiagnostics, transcribe_media
from .translation_service import translate_segments

VideoSubtitleSourceLanguage = Literal["zh", "en"]
VideoSubtitlePipeline = Literal[
    "transcribeOnly",
    "transcribeAndTranslate",
    "alignAndTranslate",
]
VIDEO_SUBTITLE_TRANSLATION_TIMEOUT_SECONDS = 120


class VideoSubtitleServiceError(ValueError):
    """Raised when the video subtitle request is invalid or not yet supported."""


@dataclass(slots=True)
class VideoSubtitleTranslationDiagnostics(JsonModel):
    provider: ProviderName
    model: str
    baseUrl: str


@dataclass(slots=True)
class VideoSubtitleDiagnostics(JsonModel):
    transcription: TranscriptionDiagnostics
    translation: VideoSubtitleTranslationDiagnostics | None = None
    alignment: SubtitleAlignmentDiagnostics | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VideoSubtitleRunResult(JsonModel):
    currentFile: ProjectFile
    segments: list[SubtitleSegment] = field(default_factory=list)
    count: int = 0
    sourceLanguage: LanguageCode = "auto"
    outputMode: OutputMode = "single"
    pipeline: VideoSubtitlePipeline = "transcribeOnly"
    status: Literal["done"] = "done"
    diagnostics: VideoSubtitleDiagnostics = field(
        default_factory=lambda: VideoSubtitleDiagnostics(
            transcription=TranscriptionDiagnostics(
                provider="localFasterWhisper",
                mode="local",
                model="small",
                providerBaseUrl=None,
                qualityPreset="balanced",
                requestedLanguage="zh",
                detectedLanguage="auto",
                preprocessingProfile="",
                rawSegmentCount=0,
                finalSegmentCount=0,
                readabilityPasses=[],
                notes=[],
            )
        )
    )


def _normalize_video_path(raw_path: str) -> Path:
    cleaned = raw_path.strip().strip('"').strip("'")
    if not cleaned:
        raise VideoSubtitleServiceError("视频文件路径不能为空。")

    path = Path(cleaned).expanduser().resolve()
    if not path.exists():
        raise VideoSubtitleServiceError(f"视频文件不存在：{path}")
    if not path.is_file():
        raise VideoSubtitleServiceError(f"所选路径不是文件：{path}")
    return path


def _normalize_subtitle_path(raw_path: str) -> Path:
    cleaned = raw_path.strip().strip('"').strip("'")
    if not cleaned:
        raise VideoSubtitleServiceError("英文字幕文件路径不能为空。")

    path = Path(cleaned).expanduser().resolve()
    if not path.exists():
        raise VideoSubtitleServiceError(f"英文字幕文件不存在：{path}")
    if not path.is_file():
        raise VideoSubtitleServiceError(f"所选字幕路径不是文件：{path}")
    if path.suffix.lower() != ".srt":
        raise VideoSubtitleServiceError("当前导入字幕分支只支持英文 SRT 文件。")
    return path


def _resolve_phase_pipeline(
    source_language: str,
    output_mode: str,
    *,
    subtitle_path: str,
) -> VideoSubtitlePipeline:
    has_subtitle_input = bool(subtitle_path.strip())

    if source_language == "zh" and output_mode == "single":
        if has_subtitle_input:
            raise VideoSubtitleServiceError(
                "当前导入英文字幕分支只支持 英语 + 双语，请先清空英文字幕文件输入。"
            )
        return "transcribeOnly"

    if source_language == "en" and output_mode == "bilingual":
        return "alignAndTranslate" if has_subtitle_input else "transcribeAndTranslate"

    raise VideoSubtitleServiceError(
        "当前只支持三种链路：中文 + 单语，英语 + 双语，或 英语 + 双语 + 英文 SRT 导入。"
    )


def _resolve_video_project_file(video_path: str) -> ProjectFile:
    normalized_path = _normalize_video_path(video_path)
    try:
        project_file = create_project_file(normalized_path)
    except UnsupportedFileTypeError as exc:
        raise VideoSubtitleServiceError(
            "当前只支持视频文件，请选择 mp4、mov 或 mkv。"
        ) from exc

    if project_file.mediaType != "video":
        raise VideoSubtitleServiceError(
            "当前只支持视频文件，请选择 mp4、mov 或 mkv。"
        )

    return project_file


def _build_translation_diagnostics(
    provider: ProviderName,
    model: str,
    base_url: str,
) -> VideoSubtitleTranslationDiagnostics:
    return VideoSubtitleTranslationDiagnostics(
        provider=provider,
        model=model,
        baseUrl=base_url,
    )


def _require_translation_config(config: AppConfig | None) -> AppConfig:
    if config is None:
        raise VideoSubtitleServiceError(
            "英语双语视频字幕需要当前翻译配置。请先在设置页保存翻译 provider 配置后再试。"
        )
    return config


def _parse_imported_subtitles(subtitle_path: str) -> list[SubtitleSegment]:
    normalized_path = _normalize_subtitle_path(subtitle_path)
    try:
        segments = parse_srt(
            file_path=normalized_path,
            source_language="en",
            target_language="zh-CN",
        )
    except SrtServiceError as exc:
        raise VideoSubtitleServiceError(str(exc)) from exc

    if not segments:
        raise VideoSubtitleServiceError("英文 SRT 中没有可用于处理的字幕段。")
    return segments


def run_video_subtitle(
    *,
    video_path: str,
    subtitle_path: str = "",
    source_language: VideoSubtitleSourceLanguage | str,
    output_mode: OutputMode | str,
    config: AppConfig | None = None,
) -> VideoSubtitleRunResult:
    resolved_source_language = str(source_language)
    resolved_output_mode = str(output_mode)
    resolved_subtitle_path = str(subtitle_path or "")
    pipeline = _resolve_phase_pipeline(
        resolved_source_language,
        resolved_output_mode,
        subtitle_path=resolved_subtitle_path,
    )
    project_file = _resolve_video_project_file(video_path)

    if pipeline == "transcribeOnly":
        transcription_result = transcribe_media(
            file_path=project_file.path,
            language=resolved_source_language,
            provider=config.defaultTranscriptionProvider if config else None,
            config=config,
        )
        diagnostics = VideoSubtitleDiagnostics(
            transcription=transcription_result.diagnostics,
            notes=["当前阶段已完成中文语音识别，并生成中文字幕。"],
        )
        segments = transcription_result.segments
        response_output_mode: OutputMode = "single"
    elif pipeline == "transcribeAndTranslate":
        transcription_result = transcribe_media(
            file_path=project_file.path,
            language=resolved_source_language,
            provider=config.defaultTranscriptionProvider if config else None,
            config=config,
        )
        resolved_config = _require_translation_config(config)
        translation_result = translate_segments(
            segments=transcription_result.segments,
            config=resolved_config,
            timeout_seconds=VIDEO_SUBTITLE_TRANSLATION_TIMEOUT_SECONDS,
        )
        diagnostics = VideoSubtitleDiagnostics(
            transcription=transcription_result.diagnostics,
            translation=_build_translation_diagnostics(
                provider=translation_result.provider,
                model=translation_result.model,
                base_url=translation_result.baseUrl,
            ),
            notes=["当前阶段已完成英语语音识别与中文字幕生成。"],
        )
        segments = translation_result.segments
        response_output_mode = "bilingual"
    else:
        resolved_config = _require_translation_config(config)
        imported_segments = _parse_imported_subtitles(resolved_subtitle_path)
        transcription_result = transcribe_media(
            file_path=project_file.path,
            language=resolved_source_language,
            provider=config.defaultTranscriptionProvider if config else None,
            config=config,
        )
        try:
            alignment_result = align_external_subtitles_to_reference(
                subtitle_segments=imported_segments,
                reference_segments=transcription_result.segments,
            )
        except SubtitleAlignmentServiceError as exc:
            raise VideoSubtitleServiceError(str(exc)) from exc

        translation_result = translate_segments(
            segments=alignment_result.segments,
            config=resolved_config,
            timeout_seconds=VIDEO_SUBTITLE_TRANSLATION_TIMEOUT_SECONDS,
        )
        diagnostics = VideoSubtitleDiagnostics(
            transcription=transcription_result.diagnostics,
            translation=_build_translation_diagnostics(
                provider=translation_result.provider,
                model=translation_result.model,
                base_url=translation_result.baseUrl,
            ),
            alignment=alignment_result.diagnostics,
            notes=[
                "当前已进入导入英文字幕分支：系统先读取英文 SRT，再参考英语语音时间轴做第一版脚手架重对齐，最后生成中文字幕。"
            ],
        )
        segments = translation_result.segments
        response_output_mode = "bilingual"

    return VideoSubtitleRunResult(
        currentFile=project_file,
        segments=segments,
        count=len(segments),
        sourceLanguage=transcription_result.sourceLanguage,
        outputMode=response_output_mode,
        pipeline=pipeline,
        status="done",
        diagnostics=diagnostics,
    )


def runVideoSubtitle(
    *,
    video_path: str,
    subtitle_path: str = "",
    source_language: VideoSubtitleSourceLanguage | str,
    output_mode: OutputMode | str,
    config: AppConfig | None = None,
) -> VideoSubtitleRunResult:
    return run_video_subtitle(
        video_path=video_path,
        subtitle_path=subtitle_path,
        source_language=source_language,
        output_mode=output_mode,
        config=config,
    )
