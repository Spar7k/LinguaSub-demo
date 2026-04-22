"""Local speech recognition with faster-whisper."""

from __future__ import annotations

import json
import logging
import math
import re
import socket
import subprocess
import tempfile
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib import error, parse, request

from .config_service import load_config
from .import_service import UnsupportedFileTypeError, detect_file_type
from .models import AppConfig, JsonModel, LanguageCode, SpeechProviderName, SubtitleSegment
from .providers import (
    BAIDU_FILE_ASYNC_CREATE_ENDPOINT,
    BAIDU_FILE_ASYNC_SPEECH_URL_EXPIRES_SECONDS,
    BAIDU_REALTIME_ENDPOINT,
    BaiduFileAsyncAsrError,
    BaiduFileAsyncConfigError,
    BaiduRealtimeAsrError,
    BaiduRealtimeConfigError,
    RealtimeSubtitlePiece,
    TencentCosUploadConfigError,
    TencentCosUploadError,
    TencentCosUploadUrlError,
    TencentFileAsyncAsrError,
    TencentFileAsyncConfigError,
    TencentRealtimeAsrError,
    TencentRealtimeConfigError,
    XFYUN_LFASR_RESULT_ENDPOINT,
    XFYUN_SPEED_CREATE_ENDPOINT,
    XFYUN_SPEED_PREPROCESSING_PROFILE,
    XfyunLfasrConfigError,
    XfyunLfasrError,
    XfyunSpeedTranscriptionConfigError,
    XfyunSpeedTranscriptionError,
    build_baidu_file_async_config,
    build_baidu_realtime_config,
    build_tencent_cos_upload_config,
    build_tencent_file_async_config,
    build_tencent_realtime_config,
    build_xfyun_lfasr_config,
    build_xfyun_speed_config,
    transcribe_with_baidu_file_async,
    transcribe_with_baidu_realtime,
    transcribe_with_tencent_file_async,
    transcribe_with_tencent_realtime,
    transcribe_with_xfyun_lfasr,
    transcribe_with_xfyun_speed_transcription,
    upload_audio_file,
    validate_baidu_realtime_connection,
    validate_tencent_realtime_connection,
)
from .speech_runtime_service import (
    FasterWhisperRuntimeUnavailableError,
    SpeechModelNotDownloadedError,
    normalize_asr_model_size,
    resolve_ffmpeg_binary,
    resolve_installed_model_path,
)

AsrLanguageInput = Literal["auto", "zh", "en", "ja", "ko", "zh-CN"]
NormalizedAsrLanguage = Literal["zh", "en", "ja", "ko"]
AsrQualityPreset = Literal["speed", "balanced", "accuracy"]
TranscriptionMode = Literal["cloud", "local"]

DEFAULT_MODEL_SIZE = "small"
DEFAULT_QUALITY_PRESET: AsrQualityPreset = "balanced"
SUPPORTED_ASR_MEDIA_TYPES = {"video", "audio"}
TARGET_LANGUAGE_FOR_TRANSLATION: LanguageCode = "zh-CN"
PREPROCESSING_PROFILE_NAME = "speech-friendly mono 16 kHz PCM WAV"
OPENAI_SPEECH_TRANSCRIPTION_MODEL = "whisper-1"
OPENAI_SPEECH_MAX_FILE_BYTES = 25 * 1024 * 1024
OPENAI_SPEECH_RESPONSE_FORMAT = "verbose_json"
OPENAI_SPEECH_TIMESTAMP_GRANULARITY = "segment"
OPENAI_SPEECH_PREPROCESSING_PROFILE = "video -> compact mono 16 kHz AAC M4A"
REALTIME_PCM_PREPROCESSING_PROFILE = "mono 16 kHz pcm_s16le raw PCM"
READABILITY_PASSES = [
    "normalize_spacing",
    "normalize_punctuation_spacing",
    "split_long_segments",
    "merge_short_segments",
]
STRONG_BREAK_CHARS = "\u3002\uFF01\uFF1F.!?;\uFF1B"
SOFT_BREAK_CHARS = "\uFF0C,\u3001:\uFF1A"
CJK_PUNCTUATION = (
    ",.;:!?%)]}\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A\u3001"
)
CJK_CHAR_PATTERN = r"\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"
CJK_CHAR_RE = re.compile(f"[{CJK_CHAR_PATTERN}]")
SPACE_RE = re.compile(r"\s+")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%])")
SPACE_AROUND_APOSTROPHE_RE = re.compile(r"(?<=\w)\s*'\s*(?=\w)")
SPACE_AROUND_HYPHEN_RE = re.compile(r"(?<=\w)\s*-\s*(?=\w)")
CJK_SPACE_RE = re.compile(
    rf"(?<=[{CJK_CHAR_PATTERN}])\s+(?=[{CJK_CHAR_PATTERN}])"
)
CJK_PUNCT_LEFT_SPACE_RE = re.compile(
    rf"(?<=[{CJK_CHAR_PATTERN}])\s+(?=[{STRONG_BREAK_CHARS}{SOFT_BREAK_CHARS}])"
)
CJK_PUNCT_RIGHT_SPACE_RE = re.compile(
    rf"(?<=[{STRONG_BREAK_CHARS}{SOFT_BREAK_CHARS}])\s+(?=[{CJK_CHAR_PATTERN}])"
)
SENTENCE_END_RE = re.compile(rf"[{STRONG_BREAK_CHARS}]$")

LOGGER = logging.getLogger("linguasub.transcription")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[LinguaSub][ASR] %(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


@dataclass(frozen=True, slots=True)
class TranscriptionQualityProfile:
    preset: AsrQualityPreset
    beamSize: int
    bestOf: int
    temperature: float
    conditionOnPreviousText: bool
    vadFilter: bool
    splitMaxDurationMs: int
    splitMaxChars: int
    mergeGapMs: int
    mergeMaxDurationMs: int
    mergeMaxChars: int
    shortSegmentMs: int
    shortSegmentChars: int


QUALITY_PROFILES: dict[AsrQualityPreset, TranscriptionQualityProfile] = {
    "speed": TranscriptionQualityProfile(
        preset="speed",
        beamSize=1,
        bestOf=1,
        temperature=0.2,
        conditionOnPreviousText=False,
        vadFilter=True,
        splitMaxDurationMs=6200,
        splitMaxChars=52,
        mergeGapMs=220,
        mergeMaxDurationMs=5600,
        mergeMaxChars=58,
        shortSegmentMs=700,
        shortSegmentChars=8,
    ),
    "balanced": TranscriptionQualityProfile(
        preset="balanced",
        beamSize=5,
        bestOf=5,
        temperature=0.0,
        conditionOnPreviousText=True,
        vadFilter=True,
        splitMaxDurationMs=5200,
        splitMaxChars=44,
        mergeGapMs=320,
        mergeMaxDurationMs=5000,
        mergeMaxChars=50,
        shortSegmentMs=820,
        shortSegmentChars=10,
    ),
    "accuracy": TranscriptionQualityProfile(
        preset="accuracy",
        beamSize=8,
        bestOf=8,
        temperature=0.0,
        conditionOnPreviousText=True,
        vadFilter=True,
        splitMaxDurationMs=4300,
        splitMaxChars=36,
        mergeGapMs=420,
        mergeMaxDurationMs=4600,
        mergeMaxChars=42,
        shortSegmentMs=960,
        shortSegmentChars=12,
    ),
}


@dataclass(slots=True)
class _SubtitlePiece:
    startMs: int
    endMs: int
    text: str


@dataclass(slots=True)
class TranscriptionDiagnostics(JsonModel):
    provider: SpeechProviderName
    mode: TranscriptionMode
    model: str
    providerBaseUrl: str | None
    qualityPreset: str
    requestedLanguage: str
    detectedLanguage: LanguageCode
    preprocessingProfile: str
    rawSegmentCount: int
    finalSegmentCount: int
    readabilityPasses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TranscriptionResult(JsonModel):
    segments: list[SubtitleSegment] = field(default_factory=list)
    sourceLanguage: LanguageCode = "auto"
    provider: SpeechProviderName = "localFasterWhisper"
    mode: TranscriptionMode = "local"
    model: str = DEFAULT_MODEL_SIZE
    qualityPreset: str = DEFAULT_QUALITY_PRESET
    diagnostics: TranscriptionDiagnostics = field(
        default_factory=lambda: TranscriptionDiagnostics(
            provider="localFasterWhisper",
            mode="local",
            model=DEFAULT_MODEL_SIZE,
            providerBaseUrl=None,
            qualityPreset=DEFAULT_QUALITY_PRESET,
            requestedLanguage="auto",
            detectedLanguage="auto",
            preprocessingProfile=PREPROCESSING_PROFILE_NAME,
            rawSegmentCount=0,
            finalSegmentCount=0,
            readabilityPasses=[],
            notes=[],
        )
    )


@dataclass(slots=True)
class SpeechConfigValidationResult(JsonModel):
    ok: bool
    provider: SpeechProviderName
    model: str
    baseUrl: str
    message: str


@dataclass(slots=True)
class ResolvedCloudTranscriptionConfig:
    provider: SpeechProviderName
    apiKey: str
    baseUrl: str
    model: str


class TranscriptionServiceError(RuntimeError):
    """Base error for local speech recognition."""


class UnsupportedTranscriptionMediaError(TranscriptionServiceError):
    """Raised when ASR is requested for a non-audio/video file."""


class MissingDependencyError(TranscriptionServiceError):
    """Raised when a required local dependency is unavailable."""


class FfmpegNotFoundError(MissingDependencyError):
    """Raised when FFmpeg is not installed or not on PATH."""


class FasterWhisperNotInstalledError(FasterWhisperRuntimeUnavailableError):
    """Raised when faster-whisper is missing."""


class MediaExtractionError(TranscriptionServiceError):
    """Raised when FFmpeg cannot prepare audio for recognition."""


class CorruptedMediaError(TranscriptionServiceError):
    """Raised when the media file cannot be decoded safely."""


class CloudTranscriptionConfigError(TranscriptionServiceError):
    """Raised when the cloud transcription route is missing API config."""


class CloudTranscriptionApiError(TranscriptionServiceError):
    """Raised when the cloud transcription provider returns an API error."""


class CloudTranscriptionFileTooLargeError(TranscriptionServiceError):
    """Raised when the cloud transcription upload is too large."""


class TranscriptionProviderAdapter(ABC):
    provider_name: SpeechProviderName
    mode: TranscriptionMode

    @abstractmethod
    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        raise NotImplementedError


def _normalize_asr_language(
    language: str | None,
) -> NormalizedAsrLanguage | None:
    if language is None:
        return None

    normalized = language.strip().lower()
    if normalized in {"", "auto"}:
        return None
    if normalized in {"zh", "zh-cn", "zh_hans", "zh-hans"}:
        return "zh"
    if normalized == "en":
        return "en"
    if normalized in {"ja", "jp"}:
        return "ja"
    if normalized == "ko":
        return "ko"

    raise TranscriptionServiceError(
        "Unsupported recognition language. Use auto, zh, en, ja, or ko."
    )


def _normalize_detected_language(language: str | None) -> LanguageCode:
    if language is None:
        return "auto"

    normalized = language.strip().lower()
    if normalized in {"zh", "zh-cn", "zh_hans", "zh-hans", "zh-tw", "zh-hk"}:
        return "zh-CN"
    if normalized == "en":
        return "en"
    if normalized in {"ja", "jp"}:
        return "ja"
    if normalized == "ko":
        return "ko"

    return "auto"


def _normalize_quality_preset(preset: str | None) -> AsrQualityPreset:
    normalized = (preset or DEFAULT_QUALITY_PRESET).strip().lower()
    if normalized in QUALITY_PROFILES:
        return normalized  # type: ignore[return-value]

    supported = ", ".join(QUALITY_PROFILES)
    raise TranscriptionServiceError(
        f"Unsupported recognition quality preset '{preset}'. Use one of: {supported}."
    )


def _normalize_transcription_provider(
    provider: str | None,
) -> SpeechProviderName:
    normalized = (provider or "baidu_realtime").strip()
    if normalized in {
        "baidu_realtime",
        "baidu_file_async",
        "tencent_realtime",
        "tencent_file_async",
        "xfyun_lfasr",
        "xfyun_speed_transcription",
        "openaiSpeech",
        "localFasterWhisper",
    }:
        return normalized  # type: ignore[return-value]

    lowered = normalized.lower()
    if lowered in {"baidu", "baidu_realtime", "baidurealtime"}:
        return "baidu_realtime"
    if lowered in {"baidu_file_async", "baidufileasync", "baidu-file-async"}:
        return "baidu_file_async"
    if lowered in {"tencent", "tencent_realtime", "tencentrealtime"}:
        return "tencent_realtime"
    if lowered in {"tencent_file_async", "tencentfileasync", "tencent-file-async"}:
        return "tencent_file_async"
    if lowered in {"xfyun_lfasr", "xfyun", "lfasr", "iflytek", "iflytek_lfasr"}:
        return "xfyun_lfasr"
    if lowered in {
        "xfyun_speed_transcription",
        "xfyun-speed-transcription",
        "xfyunspeedtranscription",
        "iflytek_speed",
        "iflytek_speed_transcription",
        "speed_transcription",
    }:
        return "xfyun_speed_transcription"
    if lowered in {"cloud", "openai", "openaispeech"}:
        return "openaiSpeech"
    if lowered in {"local", "faster-whisper", "fasterwhisper"}:
        return "localFasterWhisper"

    raise TranscriptionServiceError(
        "Unsupported transcription provider "
        f"'{provider}'. Use baidu_realtime, baidu_file_async, tencent_realtime, tencent_file_async, xfyun_lfasr, xfyun_speed_transcription, openaiSpeech, or localFasterWhisper."
    )


def _resolve_transcription_config(config: AppConfig | None) -> AppConfig:
    return config if config is not None else load_config()


def _resolve_selected_transcription_provider(
    config: AppConfig,
    provider: str | None = None,
) -> SpeechProviderName:
    return _normalize_transcription_provider(
        provider or config.speechProvider or config.defaultTranscriptionProvider
    )


def _validate_cloud_transcription_config(config: AppConfig) -> None:
    if not config.speechApiKey.strip():
        raise CloudTranscriptionConfigError(
            "Cloud transcription needs an API key. Open Settings and save the OpenAI Speech-to-Text API key first."
        )
    if not config.speechBaseUrl.strip():
        raise CloudTranscriptionConfigError(
            "Cloud transcription needs a base URL. Open Settings and save the OpenAI Speech-to-Text base URL first."
        )
    if not config.speechModel.strip():
        raise CloudTranscriptionConfigError(
            "Cloud transcription needs a model name. Open Settings and save the speech model first."
        )


def _build_baidu_realtime_config(config: AppConfig):
    try:
        return build_baidu_realtime_config(
            app_id=config.baiduAppId,
            api_key=config.baiduApiKey,
            dev_pid=config.baiduDevPid,
            cuid=config.baiduCuid,
        )
    except BaiduRealtimeConfigError as exc:
        raise CloudTranscriptionConfigError(str(exc)) from exc


def _build_baidu_file_async_config(config: AppConfig):
    try:
        return build_baidu_file_async_config(
            app_id=config.baiduFileAppId,
            api_key=config.baiduFileApiKey,
            secret_key=config.baiduFileSecretKey,
            dev_pid=config.baiduFileDevPid,
        )
    except BaiduFileAsyncConfigError as exc:
        raise CloudTranscriptionConfigError(str(exc)) from exc
    except BaiduFileAsyncAsrError as exc:
        raise CloudTranscriptionApiError(str(exc)) from exc


def _build_tencent_realtime_config(config: AppConfig):
    try:
        return build_tencent_realtime_config(
            app_id=config.tencentAppId,
            secret_id=config.tencentSecretId,
            secret_key=config.tencentSecretKey,
            engine_model_type=config.tencentEngineModelType,
        )
    except TencentRealtimeConfigError as exc:
        raise CloudTranscriptionConfigError(str(exc)) from exc
    except TencentRealtimeAsrError as exc:
        raise CloudTranscriptionApiError(str(exc)) from exc


def _build_tencent_file_async_config(config: AppConfig):
    try:
        return build_tencent_file_async_config(
            secret_id=config.tencentFileSecretId,
            secret_key=config.tencentFileSecretKey,
            engine_model_type=config.tencentFileEngineModelType,
        )
    except TencentFileAsyncConfigError as exc:
        raise CloudTranscriptionConfigError(str(exc)) from exc
    except TencentFileAsyncAsrError as exc:
        raise CloudTranscriptionApiError(str(exc)) from exc


def _build_xfyun_lfasr_config(config: AppConfig):
    try:
        return build_xfyun_lfasr_config(
            app_id=config.xfyunAppId,
            secret_key=config.xfyunSecretKey,
        )
    except XfyunLfasrConfigError as exc:
        raise CloudTranscriptionConfigError(str(exc)) from exc
    except XfyunLfasrError as exc:
        raise CloudTranscriptionApiError(str(exc)) from exc


def _build_xfyun_speed_config(config: AppConfig):
    try:
        return build_xfyun_speed_config(
            app_id=config.xfyunSpeedAppId,
            api_key=config.xfyunSpeedApiKey,
            api_secret=config.xfyunSpeedApiSecret,
        )
    except XfyunSpeedTranscriptionConfigError as exc:
        raise CloudTranscriptionConfigError(str(exc)) from exc
    except XfyunSpeedTranscriptionError as exc:
        raise CloudTranscriptionApiError(str(exc)) from exc


def _build_cos_upload_config(
    config: AppConfig,
    *,
    url_expires_seconds: int | None = None,
):
    try:
        return build_tencent_cos_upload_config(
            secret_id=config.uploadCosSecretId,
            secret_key=config.uploadCosSecretKey,
            bucket=config.uploadCosBucket,
            region=config.uploadCosRegion,
            url_expires_seconds=url_expires_seconds or 60 * 60,
        )
    except TencentCosUploadConfigError as exc:
        raise CloudTranscriptionConfigError(str(exc)) from exc
    except TencentCosUploadUrlError as exc:
        raise CloudTranscriptionApiError(str(exc)) from exc
    except TencentCosUploadError as exc:
        raise CloudTranscriptionApiError(str(exc)) from exc


def _build_baidu_file_async_speech_url_guidance() -> str:
    return (
        "百度音频文件转写需要公网可访问的 baiduFileSpeechUrl；"
        "如果不提供该 URL，则需要补全腾讯 COS 上传配置以生成临时外网 URL。"
    )


def _resolve_baidu_file_async_speech_url(config: AppConfig) -> str | None:
    speech_url = str(config.baiduFileSpeechUrl).strip()
    if not speech_url:
        return None

    lowered = speech_url.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return speech_url

    raise CloudTranscriptionConfigError(
        f"{_build_baidu_file_async_speech_url_guidance()} "
        "当前 baiduFileSpeechUrl 必须以 http:// 或 https:// 开头。"
    )


def _is_local_provider(provider: SpeechProviderName) -> bool:
    return provider == "localFasterWhisper"


def _is_cloud_provider(provider: SpeechProviderName) -> bool:
    return not _is_local_provider(provider)


def _resolve_cloud_transcription_config(
    config: AppConfig,
) -> ResolvedCloudTranscriptionConfig:
    _validate_cloud_transcription_config(config)
    return ResolvedCloudTranscriptionConfig(
        provider="openaiSpeech",
        apiKey=config.speechApiKey,
        baseUrl=config.speechBaseUrl.strip(),
        model=config.speechModel.strip() or OPENAI_SPEECH_TRANSCRIPTION_MODEL,
    )


def _build_cloud_transcription_context(
    resolved_config: ResolvedCloudTranscriptionConfig,
) -> str:
    return (
        f"provider={resolved_config.provider} "
        f"model={resolved_config.model or '<missing>'} "
        f"base_url={resolved_config.baseUrl or '<missing>'}"
    )


def _looks_like_corrupted_media(message: str) -> bool:
    lowered = message.lower()
    keywords = (
        "invalid data",
        "moov atom not found",
        "error opening input",
        "failed to read frame",
        "could not open",
        "end of file",
        "corrupt",
    )
    return any(keyword in lowered for keyword in keywords)


def _looks_like_filter_compatibility_error(message: str) -> bool:
    lowered = message.lower()
    keywords = (
        "no such filter",
        "error initializing filter",
        "error reinitializing filters",
        "error while processing the decoded data",
    )
    return any(keyword in lowered for keyword in keywords)


def _load_whisper_model_class() -> Any:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise FasterWhisperNotInstalledError(
            "The faster-whisper runtime is not available. Reinstall LinguaSub or rebuild "
            "the packaged backend sidecar with faster-whisper included."
        ) from exc

    return WhisperModel


def _create_whisper_model(model_size: str) -> Any:
    normalized_model_size = normalize_asr_model_size(model_size)
    model_path = resolve_installed_model_path(normalized_model_size)
    if model_path is None:
        raise SpeechModelNotDownloadedError(
            f"The '{normalized_model_size}' speech model is not downloaded yet. "
            "Open Import -> Environment and download the model before starting media recognition."
        )

    whisper_model_class = _load_whisper_model_class()

    try:
        return whisper_model_class(
            str(model_path),
            device="cpu",
            compute_type="int8",
        )
    except Exception as exc:  # pragma: no cover - depends on local runtime
        message = str(exc).strip() or exc.__class__.__name__
        raise TranscriptionServiceError(
            f"Could not load faster-whisper model '{normalized_model_size}' from "
            f"'{model_path}'. {message}"
        ) from exc


def _build_ffmpeg_command(
    ffmpeg_binary: Path,
    input_path: Path,
    output_path: Path,
    filters: list[str],
) -> list[str]:
    command = [
        str(ffmpeg_binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-map",
        "0:a:0?",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        "-c:a",
        "pcm_s16le",
    ]

    if filters:
        command.extend(["-af", ",".join(filters)])

    command.extend(["-f", "wav", str(output_path)])
    return command


def _run_ffmpeg_command(command: list[str]) -> None:
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _build_cloud_ffmpeg_command(
    ffmpeg_binary: Path,
    input_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        str(ffmpeg_binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-map",
        "0:a:0?",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "aac",
        "-b:a",
        "48k",
        str(output_path),
    ]


def _build_realtime_pcm_ffmpeg_command(
    ffmpeg_binary: Path,
    input_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        str(ffmpeg_binary),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-map",
        "0:a:0?",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        "-c:a",
        "pcm_s16le",
        "-f",
        "s16le",
        str(output_path),
    ]


def _extract_audio_with_ffmpeg(input_path: Path, output_path: Path) -> None:
    ffmpeg_binary = resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        raise FfmpegNotFoundError(
            "FFmpeg is not available. Reinstall LinguaSub with bundled ffmpeg.exe or "
            "configure a local FFmpeg binary."
        )

    filter_variants = [
        [
            "highpass=f=80",
            "lowpass=f=7600",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
        ],
        [
            "highpass=f=80",
            "lowpass=f=7600",
        ],
    ]

    last_error: subprocess.CalledProcessError | None = None
    for attempt_index, filters in enumerate(filter_variants, start=1):
        command = _build_ffmpeg_command(ffmpeg_binary, input_path, output_path, filters)
        LOGGER.info(
            "Audio preprocessing attempt %s for '%s' with filters: %s",
            attempt_index,
            input_path.name,
            ", ".join(filters) or "none",
        )
        try:
            _run_ffmpeg_command(command)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            message = (exc.stderr or exc.stdout or "").strip() or "Unknown FFmpeg error."
            if _looks_like_corrupted_media(message):
                raise CorruptedMediaError(
                    f"Could not read media file '{input_path.name}'. {message}"
                ) from exc
            if attempt_index < len(filter_variants) and _looks_like_filter_compatibility_error(
                message
            ):
                LOGGER.info(
                    "FFmpeg filter fallback for '%s' after compatibility error: %s",
                    input_path.name,
                    message,
                )
                continue

            raise MediaExtractionError(
                f"FFmpeg could not prepare audio from '{input_path.name}'. {message}"
            ) from exc

    if last_error is not None:
        message = (last_error.stderr or last_error.stdout or "").strip()
        raise MediaExtractionError(
            f"FFmpeg could not prepare audio from '{input_path.name}'. {message}"
        ) from last_error


def _extract_audio_for_cloud_transcription(input_path: Path, output_path: Path) -> None:
    ffmpeg_binary = resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        raise FfmpegNotFoundError(
            "FFmpeg is not available. Reinstall LinguaSub with bundled ffmpeg.exe or configure a local FFmpeg binary."
        )

    command = _build_cloud_ffmpeg_command(ffmpeg_binary, input_path, output_path)
    LOGGER.info(
        "Preparing cloud transcription audio for '%s' with compact AAC settings.",
        input_path.name,
    )
    try:
        _run_ffmpeg_command(command)
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip() or "Unknown FFmpeg error."
        if _looks_like_corrupted_media(message):
            raise CorruptedMediaError(
                f"Could not read media file '{input_path.name}'. {message}"
            ) from exc
        raise MediaExtractionError(
            f"FFmpeg could not prepare cloud transcription audio from '{input_path.name}'. {message}"
        ) from exc


def _extract_pcm_for_realtime_transcription(
    input_path: Path,
    output_path: Path,
    provider_label: str,
) -> None:
    ffmpeg_binary = resolve_ffmpeg_binary()
    if ffmpeg_binary is None:
        raise FfmpegNotFoundError(
            "FFmpeg is not available. Reinstall LinguaSub with bundled ffmpeg.exe or configure a local FFmpeg binary."
        )

    command = _build_realtime_pcm_ffmpeg_command(ffmpeg_binary, input_path, output_path)
    LOGGER.info(
        "Preparing realtime PCM audio for '%s' provider=%s with mono 16k pcm_s16le.",
        input_path.name,
        provider_label,
    )
    try:
        _run_ffmpeg_command(command)
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip() or "Unknown FFmpeg error."
        if _looks_like_corrupted_media(message):
            raise CorruptedMediaError(
                f"Could not read media file '{input_path.name}'. {message}"
            ) from exc
        raise MediaExtractionError(
            f"FFmpeg could not prepare realtime PCM audio from '{input_path.name}'. {message}"
        ) from exc

    LOGGER.info(
        "Realtime PCM conversion finished provider=%s source='%s' output='%s'",
        provider_label,
        input_path.name,
        output_path.name,
    )


@contextmanager
def _prepare_audio_input(file_path: Path) -> Iterator[Path]:
    try:
        media_type = detect_file_type(file_path)
    except UnsupportedFileTypeError as exc:
        raise UnsupportedTranscriptionMediaError(str(exc)) from exc

    if media_type not in SUPPORTED_ASR_MEDIA_TYPES:
        raise UnsupportedTranscriptionMediaError(
            f"Speech recognition only supports audio or video files, not '{media_type}'."
        )

    with tempfile.TemporaryDirectory(prefix="linguasub-asr-") as temp_dir:
        output_path = Path(temp_dir) / f"{file_path.stem}.speech.wav"
        _extract_audio_with_ffmpeg(file_path, output_path)
        yield output_path


@contextmanager
def _prepare_cloud_audio_input(file_path: Path) -> Iterator[Path]:
    try:
        media_type = detect_file_type(file_path)
    except UnsupportedFileTypeError as exc:
        raise UnsupportedTranscriptionMediaError(str(exc)) from exc

    if media_type not in SUPPORTED_ASR_MEDIA_TYPES:
        raise UnsupportedTranscriptionMediaError(
            f"Speech recognition only supports audio or video files, not '{media_type}'."
        )

    if media_type == "audio":
        yield file_path
        return

    with tempfile.TemporaryDirectory(prefix="linguasub-cloud-asr-") as temp_dir:
        output_path = Path(temp_dir) / f"{file_path.stem}.speech.m4a"
        _extract_audio_for_cloud_transcription(file_path, output_path)
        yield output_path


@contextmanager
def _prepare_realtime_pcm_input(
    file_path: Path,
    provider_label: str,
) -> Iterator[Path]:
    try:
        media_type = detect_file_type(file_path)
    except UnsupportedFileTypeError as exc:
        raise UnsupportedTranscriptionMediaError(str(exc)) from exc

    if media_type not in SUPPORTED_ASR_MEDIA_TYPES:
        raise UnsupportedTranscriptionMediaError(
            f"Speech recognition only supports audio or video files, not '{media_type}'."
        )

    with tempfile.TemporaryDirectory(prefix="linguasub-realtime-asr-") as temp_dir:
        output_path = Path(temp_dir) / f"{file_path.stem}.speech.pcm"
        _extract_pcm_for_realtime_transcription(file_path, output_path, provider_label)
        yield output_path


def _is_cjk_character(character: str) -> bool:
    return bool(character and CJK_CHAR_RE.match(character))


def _contains_cjk(text: str) -> bool:
    return bool(CJK_CHAR_RE.search(text))


def _clean_transcribed_text(text: str, language: LanguageCode) -> str:
    cleaned = SPACE_RE.sub(" ", text.replace("\u3000", " ")).strip()
    if not cleaned:
        return ""

    cleaned = SPACE_AROUND_APOSTROPHE_RE.sub("'", cleaned)
    cleaned = SPACE_AROUND_HYPHEN_RE.sub("-", cleaned)
    cleaned = SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)

    if language in {"zh-CN", "ja", "ko"} or _contains_cjk(cleaned):
        cleaned = CJK_SPACE_RE.sub("", cleaned)
        cleaned = CJK_PUNCT_LEFT_SPACE_RE.sub("", cleaned)
        cleaned = CJK_PUNCT_RIGHT_SPACE_RE.sub("", cleaned)

    return cleaned.strip()


def _needs_space_between(left: str, right: str) -> bool:
    if not left or not right:
        return False

    last_character = left[-1]
    first_character = right[0]
    if last_character.isspace() or first_character.isspace():
        return False
    if first_character in CJK_PUNCTUATION:
        return False
    if last_character in "([{/$":
        return False
    if _is_cjk_character(last_character) or _is_cjk_character(first_character):
        return False

    return True


def _join_text_parts(parts: list[str]) -> str:
    if not parts:
        return ""

    combined = parts[0]
    for part in parts[1:]:
        if _needs_space_between(combined, part):
            combined = f"{combined} {part}"
        else:
            combined = f"{combined}{part}"
    return combined


def _split_on_breaks(text: str, break_chars: str) -> list[str]:
    pieces: list[str] = []
    buffer: list[str] = []
    for character in text:
        buffer.append(character)
        if character in break_chars:
            piece = "".join(buffer).strip()
            if piece:
                pieces.append(piece)
            buffer = []

    trailing_piece = "".join(buffer).strip()
    if trailing_piece:
        pieces.append(trailing_piece)
    return pieces or [text.strip()]


def _split_tokens_evenly(text: str, target_piece_count: int) -> list[str]:
    if target_piece_count <= 1:
        return [text.strip()]

    if " " in text:
        tokens = [token for token in text.split(" ") if token]
        if len(tokens) <= 1:
            return [text.strip()]
        joiner = " "
    else:
        tokens = [character for character in text if character.strip()]
        if len(tokens) <= 1:
            return [text.strip()]
        joiner = ""

    chunk_size = max(1, math.ceil(len(tokens) / target_piece_count))
    parts = [
        joiner.join(tokens[index : index + chunk_size]).strip()
        for index in range(0, len(tokens), chunk_size)
    ]
    return [part for part in parts if part]


def _split_text_for_readability(
    text: str,
    max_chars: int,
    target_piece_count: int,
) -> list[str]:
    effective_limit = max(10, max_chars)

    candidate_sets = [
        _split_on_breaks(text, STRONG_BREAK_CHARS),
        _split_on_breaks(text, f"{STRONG_BREAK_CHARS}{SOFT_BREAK_CHARS}"),
    ]

    for clauses in candidate_sets:
        parts: list[str] = []
        current_parts: list[str] = []
        for clause in clauses:
            proposed = (
                _join_text_parts([*current_parts, clause])
                if current_parts
                else clause
            )
            if current_parts and len(proposed) > effective_limit:
                parts.append(_join_text_parts(current_parts))
                current_parts = [clause]
            else:
                current_parts.append(clause)
        if current_parts:
            parts.append(_join_text_parts(current_parts))

        if len(parts) >= target_piece_count and all(
            len(part) <= effective_limit for part in parts
        ):
            return parts

    even_parts = _split_tokens_evenly(text, target_piece_count)
    if len(even_parts) > 1:
        return even_parts

    return [
        text[index : index + effective_limit].strip()
        for index in range(0, len(text), effective_limit)
        if text[index : index + effective_limit].strip()
    ]


def _text_weight(text: str) -> int:
    weight = 0
    for character in text:
        if character.isspace():
            continue
        weight += 2 if _is_cjk_character(character) else 1
    return max(weight, 1)


def _split_piece_timing(
    piece: _SubtitlePiece,
    text_parts: list[str],
) -> list[_SubtitlePiece]:
    if len(text_parts) <= 1:
        return [piece]

    total_duration = max(piece.endMs - piece.startMs, len(text_parts))
    weights = [_text_weight(part) for part in text_parts]
    total_weight = sum(weights)
    boundaries = [piece.startMs]
    consumed_weight = 0

    for index, weight in enumerate(weights[:-1], start=1):
        consumed_weight += weight
        proportional_end = piece.startMs + round(
            total_duration * consumed_weight / total_weight
        )
        minimum_end = boundaries[-1] + 1
        maximum_end = piece.endMs - (len(weights) - index)
        boundaries.append(max(minimum_end, min(proportional_end, maximum_end)))

    boundaries.append(piece.endMs)

    split_pieces: list[_SubtitlePiece] = []
    for index, text_part in enumerate(text_parts):
        start_ms = boundaries[index]
        end_ms = boundaries[index + 1]
        if end_ms <= start_ms:
            end_ms = start_ms + 1
        split_pieces.append(
            _SubtitlePiece(
                startMs=start_ms,
                endMs=end_ms,
                text=text_part,
            )
        )

    return split_pieces


def _split_long_piece(
    piece: _SubtitlePiece,
    profile: TranscriptionQualityProfile,
) -> list[_SubtitlePiece]:
    duration_ms = max(piece.endMs - piece.startMs, 1)
    target_piece_count = max(
        1,
        math.ceil(duration_ms / profile.splitMaxDurationMs),
        math.ceil(len(piece.text) / profile.splitMaxChars),
    )
    if target_piece_count <= 1:
        return [piece]

    suggested_limit = min(
        profile.splitMaxChars,
        max(10, math.ceil(len(piece.text) / target_piece_count)),
    )
    text_parts = _split_text_for_readability(
        piece.text,
        max_chars=suggested_limit,
        target_piece_count=target_piece_count,
    )
    return _split_piece_timing(piece, text_parts)


def _should_merge_pieces(
    left: _SubtitlePiece,
    right: _SubtitlePiece,
    profile: TranscriptionQualityProfile,
) -> bool:
    gap_ms = max(0, right.startMs - left.endMs)
    if gap_ms > profile.mergeGapMs:
        return False

    combined_text = _join_text_parts([left.text, right.text])
    combined_duration = right.endMs - left.startMs
    left_is_short = (
        len(left.text) <= profile.shortSegmentChars
        or (left.endMs - left.startMs) <= profile.shortSegmentMs
    )
    right_is_short = (
        len(right.text) <= profile.shortSegmentChars
        or (right.endMs - right.startMs) <= profile.shortSegmentMs
    )
    left_ends_sentence = bool(SENTENCE_END_RE.search(left.text))

    return (
        combined_duration <= profile.mergeMaxDurationMs
        and len(combined_text) <= profile.mergeMaxChars
        and (left_is_short or right_is_short or not left_ends_sentence)
    )


def _apply_readability_cleanup(
    raw_pieces: list[_SubtitlePiece],
    profile: TranscriptionQualityProfile,
    detected_language: LanguageCode,
) -> list[_SubtitlePiece]:
    split_pieces: list[_SubtitlePiece] = []
    for piece in raw_pieces:
        cleaned_text = _clean_transcribed_text(piece.text, detected_language)
        if not cleaned_text:
            continue

        cleaned_piece = _SubtitlePiece(
            startMs=piece.startMs,
            endMs=max(piece.endMs, piece.startMs + 1),
            text=cleaned_text,
        )
        split_pieces.extend(_split_long_piece(cleaned_piece, profile))

    merged_pieces: list[_SubtitlePiece] = []
    for piece in split_pieces:
        if merged_pieces and _should_merge_pieces(merged_pieces[-1], piece, profile):
            previous = merged_pieces[-1]
            merged_pieces[-1] = _SubtitlePiece(
                startMs=previous.startMs,
                endMs=piece.endMs,
                text=_join_text_parts([previous.text, piece.text]),
            )
            continue

        merged_pieces.append(piece)

    return merged_pieces


def _build_decode_options(
    language: str | None,
    profile: TranscriptionQualityProfile,
) -> dict[str, Any]:
    return {
        "language": language,
        "beam_size": profile.beamSize,
        "best_of": profile.bestOf,
        "temperature": profile.temperature,
        "condition_on_previous_text": profile.conditionOnPreviousText,
        "vad_filter": profile.vadFilter,
    }


def _build_subtitle_segments(
    pieces: list[_SubtitlePiece],
    detected_language: LanguageCode,
) -> list[SubtitleSegment]:
    segments: list[SubtitleSegment] = []
    for index, piece in enumerate(pieces, start=1):
        if not piece.text:
            continue

        segments.append(
            SubtitleSegment(
                id=f"seg-{index:03d}",
                start=piece.startMs,
                end=piece.endMs,
                sourceText=piece.text,
                translatedText="",
                sourceLanguage=detected_language,
                targetLanguage=TARGET_LANGUAGE_FOR_TRANSLATION,
            )
        )
    return segments


def _realtime_pieces_to_internal(
    pieces: list[RealtimeSubtitlePiece],
) -> list[_SubtitlePiece]:
    return [
        _SubtitlePiece(
            startMs=max(0, int(piece.startMs)),
            endMs=max(int(piece.endMs), int(piece.startMs) + 1),
            text=str(piece.text),
        )
        for piece in pieces
        if str(piece.text).strip()
    ]


def _infer_cloud_language_from_hint(
    provider: SpeechProviderName,
    requested_language: str | None,
    model_name: str,
) -> LanguageCode:
    normalized_requested = _normalize_detected_language(requested_language)
    if normalized_requested != "auto":
        return normalized_requested

    lowered_model = model_name.strip().lower()
    if provider in {"baidu_realtime", "baidu_file_async"}:
        if lowered_model.startswith("17") or lowered_model.startswith("16"):
            return "en"
        return "zh-CN"
    if provider in {"tencent_realtime", "tencent_file_async"}:
        if "_en" in lowered_model or lowered_model.endswith("en"):
            return "en"
        if "_ja" in lowered_model:
            return "ja"
        if "_ko" in lowered_model:
            return "ko"
        return "zh-CN"
    if provider in {"xfyun_lfasr", "xfyun_speed_transcription"}:
        return "zh-CN"

    return "auto"


def _build_realtime_cloud_result(
    *,
    provider: SpeechProviderName,
    model_name: str,
    endpoint_url: str,
    requested_language: str | None,
    preprocessing_profile: str,
    raw_pieces: list[RealtimeSubtitlePiece],
    notes: list[str],
) -> TranscriptionResult:
    detected_language = _infer_cloud_language_from_hint(
        provider,
        requested_language,
        model_name,
    )
    internal_pieces = _realtime_pieces_to_internal(raw_pieces)
    if not internal_pieces:
        raise CloudTranscriptionApiError("云端识别没有返回可用的句级结果。")

    cleaned_pieces = _apply_readability_cleanup(
        internal_pieces,
        QUALITY_PROFILES["balanced"],
        detected_language,
    )
    subtitle_segments = _build_subtitle_segments(cleaned_pieces, detected_language)
    diagnostics = TranscriptionDiagnostics(
        provider=provider,
        mode="cloud",
        model=model_name,
        providerBaseUrl=endpoint_url,
        qualityPreset="cloudRealtime",
        requestedLanguage=requested_language or "auto",
        detectedLanguage=detected_language,
        preprocessingProfile=preprocessing_profile,
        rawSegmentCount=len(internal_pieces),
        finalSegmentCount=len(subtitle_segments),
        readabilityPasses=list(READABILITY_PASSES),
        notes=notes,
    )
    return TranscriptionResult(
        segments=subtitle_segments,
        sourceLanguage=detected_language,
        provider=provider,
        mode="cloud",
        model=model_name,
        qualityPreset="cloudRealtime",
        diagnostics=diagnostics,
    )


def _transcribe_audio_file(
    audio_path: Path,
    language: str | None,
    model_size: str,
    quality_preset: AsrQualityPreset,
) -> TranscriptionResult:
    profile = QUALITY_PROFILES[quality_preset]
    model = _create_whisper_model(model_size)
    decode_options = _build_decode_options(language, profile)

    LOGGER.info(
        "Starting ASR for '%s' with model=%s preset=%s language=%s",
        audio_path.name,
        normalize_asr_model_size(model_size),
        quality_preset,
        language or "auto",
    )

    try:
        whisper_segments, info = model.transcribe(str(audio_path), **decode_options)
        detected_language = _normalize_detected_language(
            getattr(info, "language", None) or language
        )
    except Exception as exc:  # pragma: no cover - depends on local runtime
        message = str(exc).strip() or exc.__class__.__name__
        if _looks_like_corrupted_media(message):
            raise CorruptedMediaError(
                f"Could not decode media file '{audio_path.name}'. {message}"
            ) from exc
        raise TranscriptionServiceError(
            f"Speech recognition failed for '{audio_path.name}'. {message}"
        ) from exc

    raw_pieces: list[_SubtitlePiece] = []
    try:
        for segment in whisper_segments:
            source_text = str(getattr(segment, "text", ""))
            start_ms = int(round(float(getattr(segment, "start", 0.0)) * 1000))
            end_ms = int(round(float(getattr(segment, "end", 0.0)) * 1000))
            raw_pieces.append(
                _SubtitlePiece(
                    startMs=start_ms,
                    endMs=max(end_ms, start_ms + 1),
                    text=source_text,
                )
            )
    except Exception as exc:  # pragma: no cover - depends on local runtime
        message = str(exc).strip() or exc.__class__.__name__
        raise TranscriptionServiceError(
            f"Could not read transcription segments from '{audio_path.name}'. {message}"
        ) from exc

    cleaned_pieces = _apply_readability_cleanup(raw_pieces, profile, detected_language)
    subtitle_segments = _build_subtitle_segments(cleaned_pieces, detected_language)
    diagnostics = TranscriptionDiagnostics(
        provider="localFasterWhisper",
        mode="local",
        model=normalize_asr_model_size(model_size),
        providerBaseUrl=None,
        qualityPreset=quality_preset,
        requestedLanguage=language or "auto",
        detectedLanguage=detected_language,
        preprocessingProfile=PREPROCESSING_PROFILE_NAME,
        rawSegmentCount=len(raw_pieces),
        finalSegmentCount=len(subtitle_segments),
        readabilityPasses=list(READABILITY_PASSES),
        notes=[
            "Raw transcription quality comes from the local faster-whisper model and decoding preset.",
            "Readability cleanup may merge or split subtitle lines after the raw ASR pass.",
        ],
    )

    LOGGER.info(
        "Finished ASR for '%s': detected=%s raw_segments=%s final_segments=%s preset=%s",
        audio_path.name,
        detected_language,
        len(raw_pieces),
        len(subtitle_segments),
        quality_preset,
    )

    return TranscriptionResult(
        segments=subtitle_segments,
        sourceLanguage=detected_language,
        provider="localFasterWhisper",
        mode="local",
        model=normalize_asr_model_size(model_size),
        qualityPreset=quality_preset,
        diagnostics=diagnostics,
    )


def _guess_audio_content_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".m4a":
        return "audio/mp4"
    return "application/octet-stream"


def _build_multipart_form_data(
    *,
    fields: list[tuple[str, str]],
    file_field_name: str,
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = f"----LinguaSubBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field_name}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {_guess_audio_content_type(file_path)}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _build_openai_speech_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/audio/transcriptions"):
        return normalized
    return f"{normalized}/audio/transcriptions"


def _build_openai_models_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/audio/transcriptions"):
        normalized = normalized[: -len("/audio/transcriptions")]
    if normalized.endswith("/models"):
        return normalized
    return f"{normalized}/models"


def _build_openai_model_detail_endpoint(base_url: str, model: str) -> str:
    normalized_model = model.strip()
    models_endpoint = _build_openai_models_endpoint(base_url).rstrip("/")
    return f"{models_endpoint}/{parse.quote(normalized_model, safe='')}"


def _get_cloud_json(
    *,
    url: str,
    api_key: str,
    timeout_seconds: int,
    context_label: str,
    request_label: str,
) -> dict[str, Any]:
    LOGGER.info(
        "Cloud speech validation request: label=%s url=%s %s",
        request_label,
        url,
        context_label,
    )
    http_request = request.Request(
        url=url,
        headers={
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            raise CloudTranscriptionApiError(
                "云端识别鉴权失败，识别 API Key 可能无效或没有权限。"
                f" 当前配置：{context_label} final_url={url} HTTP {exc.code}. {error_text}"
            ) from exc
        if exc.code == 404:
            if request_label == "model-check":
                raise CloudTranscriptionApiError(
                    "识别模型无效，或当前服务地址不支持该模型校验接口。"
                    f" 当前配置：{context_label} final_url={url} HTTP 404. {error_text}"
                ) from exc
            raise CloudTranscriptionApiError(
                "云端识别服务地址不可用，或接口路径拼接错误。"
                f" 当前配置：{context_label} final_url={url} HTTP 404. {error_text}"
            ) from exc
        raise CloudTranscriptionApiError(
            f"云端识别连接失败。当前配置：{context_label} "
            f"final_url={url} HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise CloudTranscriptionApiError(
            "云端识别连接失败，可能是服务地址错误或网络不可达。"
            f" 当前配置：{context_label} final_url={url}. {exc.reason}"
        ) from exc
    except socket.timeout as exc:
        raise CloudTranscriptionApiError(
            f"云端识别连接超时。当前配置：{context_label} final_url={url}."
        ) from exc
    except TimeoutError as exc:
        raise CloudTranscriptionApiError(
            f"云端识别连接超时。当前配置：{context_label} final_url={url}."
        ) from exc

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise CloudTranscriptionApiError(
            f"云端识别连接返回了无法解析的数据。当前配置：{context_label} final_url={url}."
        ) from exc

    LOGGER.info(
        "Cloud speech validation request: label=%s url=%s %s",
        request_label,
        url,
        context_label,
    )
    http_request = request.Request(
        url=url,
        headers={
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            raise CloudTranscriptionApiError(
                f"云端识别鉴权失败，识别 API Key 可能无效或没有权限。"
                f" 当前配置：{context_label} final_url={url} HTTP {exc.code}. {error_text}"
            ) from exc
        if exc.code == 404:
            if request_label == "model-check":
                raise CloudTranscriptionApiError(
                    f"识别模型无效，或当前服务地址不支持该模型校验接口。"
                    f" 当前配置：{context_label} final_url={url} HTTP 404. {error_text}"
                ) from exc
            raise CloudTranscriptionApiError(
                f"云端识别服务地址不可用，或接口路径拼接错误。"
                f" 当前配置：{context_label} final_url={url} HTTP 404. {error_text}"
            ) from exc
        raise CloudTranscriptionApiError(
            f"云端识别连接失败。当前配置：{context_label} "
            f"final_url={url} HTTP {exc.code}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise CloudTranscriptionApiError(
            f"云端识别连接失败，可能是服务地址错误或网络不可达。"
            f" 当前配置：{context_label} final_url={url}. {exc.reason}"
        ) from exc
    except socket.timeout as exc:
        raise CloudTranscriptionApiError(
            f"云端识别连接超时。当前配置：{context_label} final_url={url}."
        ) from exc
    except TimeoutError as exc:
        raise CloudTranscriptionApiError(
            f"云端识别连接超时。当前配置：{context_label} final_url={url}."
        ) from exc

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise CloudTranscriptionApiError(
            f"云端识别连接返回了无法解析的数据。"
            f" 当前配置：{context_label} final_url={url}."
        ) from exc


def _post_cloud_transcription_request(
    *,
    url: str,
    api_key: str,
    body: bytes,
    content_type: str,
    timeout_seconds: int,
    context_label: str,
) -> dict[str, Any]:
    http_request = request.Request(
        url=url,
        data=body,
        headers={
            "Content-Type": content_type,
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise CloudTranscriptionApiError(
            f"Cloud transcription request failed with HTTP {exc.code} while using "
            f"{context_label}. {error_text}"
        ) from exc
    except error.URLError as exc:
        raise CloudTranscriptionApiError(
            f"Cloud transcription request hit a network error while using "
            f"{context_label}. {exc.reason}"
        ) from exc
    except socket.timeout as exc:
        raise CloudTranscriptionApiError(
            f"Cloud transcription request timed out while using {context_label}."
        ) from exc
    except TimeoutError as exc:
        raise CloudTranscriptionApiError(
            f"Cloud transcription request timed out while using {context_label}."
        ) from exc

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise CloudTranscriptionApiError(
            f"Cloud transcription returned invalid JSON while using {context_label}."
        ) from exc


def validate_speech_config(
    config: AppConfig,
    timeout_seconds: int = 20,
) -> SpeechConfigValidationResult:
    selected_provider = _resolve_selected_transcription_provider(config)

    if selected_provider == "baidu_realtime":
        baidu_config = _build_baidu_realtime_config(config)
        try:
            validate_baidu_realtime_connection(
                baidu_config,
                timeout_seconds=timeout_seconds,
            )
        except BaiduRealtimeAsrError as exc:
            raise CloudTranscriptionApiError(str(exc)) from exc

        return SpeechConfigValidationResult(
            ok=True,
            provider=selected_provider,
            model=baidu_config.devPid,
            baseUrl=BAIDU_REALTIME_ENDPOINT,
            message=(
                "百度实时识别连接测试成功。"
                f" provider=baidu_realtime dev_pid={baidu_config.devPid} "
                f"endpoint={BAIDU_REALTIME_ENDPOINT}"
            ),
        )

    if selected_provider == "baidu_file_async":
        raise CloudTranscriptionConfigError(
            "Baidu file async validation is not implemented yet. "
            "You can still save the config and use the transcription workflow directly."
        )

    if selected_provider == "tencent_realtime":
        tencent_config = _build_tencent_realtime_config(config)
        try:
            validate_tencent_realtime_connection(
                tencent_config,
                timeout_seconds=timeout_seconds,
            )
        except TencentRealtimeAsrError as exc:
            raise CloudTranscriptionApiError(str(exc)) from exc

        return SpeechConfigValidationResult(
            ok=True,
            provider=selected_provider,
            model=tencent_config.engineModelType,
            baseUrl=f"wss://asr.cloud.tencent.com/asr/v2/{tencent_config.appId}",
            message=(
                "腾讯实时识别连接测试成功。"
                f" provider=tencent_realtime engine_model_type={tencent_config.engineModelType} "
                f"endpoint=wss://asr.cloud.tencent.com/asr/v2/{tencent_config.appId}"
            ),
        )

    if selected_provider == "tencent_file_async":
        raise CloudTranscriptionConfigError(
            "Tencent file async validation is not implemented yet. "
            "You can still save the config and use the transcription workflow directly."
        )

    if selected_provider == "xfyun_lfasr":
        raise CloudTranscriptionConfigError(
            "XFYUN LFASR validation is not implemented yet. "
            "You can still save the config and use the transcription workflow directly."
        )

    if selected_provider == "xfyun_speed_transcription":
        raise CloudTranscriptionConfigError(
            "XFYUN speed transcription validation is not implemented yet. "
            "You can still save the config and use the transcription workflow directly."
        )

    if selected_provider == "localFasterWhisper":
        return SpeechConfigValidationResult(
            ok=True,
            provider=selected_provider,
            model=normalize_asr_model_size(DEFAULT_MODEL_SIZE),
            baseUrl="local://faster-whisper",
            message="当前已切换到本地识别模式，无需测试云端连接。",
        )

    resolved_config = _resolve_cloud_transcription_config(config)
    models_url = _build_openai_models_endpoint(resolved_config.baseUrl)
    response_payload = _get_cloud_json(
        url=models_url,
        api_key=resolved_config.apiKey,
        timeout_seconds=timeout_seconds,
        context_label=_build_cloud_transcription_context(resolved_config),
        request_label="models-list",
    )
    if not isinstance(response_payload, dict):
        raise CloudTranscriptionApiError("云端识别服务返回了异常的模型列表响应。")

    model_url = _build_openai_model_detail_endpoint(
        resolved_config.baseUrl,
        resolved_config.model,
    )
    model_payload = _get_cloud_json(
        url=model_url,
        api_key=resolved_config.apiKey,
        timeout_seconds=timeout_seconds,
        context_label=_build_cloud_transcription_context(resolved_config),
        request_label="model-check",
    )
    if not isinstance(model_payload, dict):
        raise CloudTranscriptionApiError("云端识别服务返回了异常的模型校验响应。")

    return SpeechConfigValidationResult(
        ok=True,
        provider=resolved_config.provider,
        model=resolved_config.model,
        baseUrl=resolved_config.baseUrl,
        message=(
            "识别连接测试成功。"
            f" 已确认 provider '{resolved_config.provider}'、模型 '{resolved_config.model}' "
            f"和服务地址 '{resolved_config.baseUrl}' 可用于云端识别。"
        ),
    )


def _parse_openai_cloud_segments(
    response_payload: dict[str, Any],
    requested_language: str | None,
    model_name: str,
    base_url: str,
) -> TranscriptionResult:
    raw_segments = response_payload.get("segments")
    detected_language = _normalize_detected_language(
        response_payload.get("language") or requested_language
    )

    if not isinstance(raw_segments, list) or not raw_segments:
        raise CloudTranscriptionApiError(
            "Verification step failed. Cloud transcription completed, but the API did not return timestamped segments."
        )

    raw_pieces: list[_SubtitlePiece] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start_ms = int(round(float(item.get("start", 0.0)) * 1000))
        end_ms = int(round(float(item.get("end", 0.0)) * 1000))
        raw_pieces.append(
            _SubtitlePiece(
                startMs=start_ms,
                endMs=max(end_ms, start_ms + 1),
                text=text,
            )
        )

    if not raw_pieces:
        raise CloudTranscriptionApiError(
            "Verification step failed. Cloud transcription did not return any usable subtitle segments."
        )

    cleaned_pieces = _apply_readability_cleanup(
        raw_pieces,
        QUALITY_PROFILES["balanced"],
        detected_language,
    )
    subtitle_segments = _build_subtitle_segments(cleaned_pieces, detected_language)
    diagnostics = TranscriptionDiagnostics(
        provider="openaiSpeech",
        mode="cloud",
        model=model_name,
        providerBaseUrl=base_url,
        qualityPreset="cloudDefault",
        requestedLanguage=requested_language or "auto",
        detectedLanguage=detected_language,
        preprocessingProfile=OPENAI_SPEECH_PREPROCESSING_PROFILE,
        rawSegmentCount=len(raw_pieces),
        finalSegmentCount=len(subtitle_segments),
        readabilityPasses=list(READABILITY_PASSES),
        notes=[
            "Raw transcription quality comes from the OpenAI cloud speech model.",
            "Readability cleanup may merge or split subtitle lines after the cloud ASR pass.",
        ],
    )
    return TranscriptionResult(
        segments=subtitle_segments,
        sourceLanguage=detected_language,
        provider="openaiSpeech",
        mode="cloud",
        model=model_name,
        qualityPreset="cloudDefault",
        diagnostics=diagnostics,
    )


class LocalFasterWhisperTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "localFasterWhisper"
    mode = "local"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        with _prepare_audio_input(file_path) as audio_path:
            return _transcribe_audio_file(
                audio_path=audio_path,
                language=language,
                model_size=model_size,
                quality_preset=quality_preset,
            )


class BaiduRealtimeTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "baidu_realtime"
    mode = "cloud"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        resolved_config = _resolve_transcription_config(config)
        baidu_config = _build_baidu_realtime_config(resolved_config)

        LOGGER.info(
            "Starting realtime ASR for '%s' with provider=baidu_realtime dev_pid=%s cuid=%s",
            file_path.name,
            baidu_config.devPid,
            baidu_config.cuid,
        )

        with _prepare_realtime_pcm_input(file_path, "baidu_realtime") as pcm_path:
            try:
                pieces = transcribe_with_baidu_realtime(pcm_path, baidu_config)
            except BaiduRealtimeAsrError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc

        result = _build_realtime_cloud_result(
            provider="baidu_realtime",
            model_name=baidu_config.devPid,
            endpoint_url=baidu_config.websocketUrl,
            requested_language=language,
            preprocessing_profile=REALTIME_PCM_PREPROCESSING_PROFILE,
            raw_pieces=pieces,
            notes=[
                "Raw transcription quality comes from Baidu realtime ASR.",
                "Audio was preprocessed to mono 16 kHz pcm_s16le before websocket streaming.",
            ],
        )
        LOGGER.info(
            "Finished realtime ASR for '%s': provider=baidu_realtime raw_segments=%s final_segments=%s",
            file_path.name,
            result.diagnostics.rawSegmentCount,
            result.diagnostics.finalSegmentCount,
        )
        return result


class BaiduFileAsyncTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "baidu_file_async"
    mode = "cloud"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        resolved_config = _resolve_transcription_config(config)
        baidu_config = _build_baidu_file_async_config(resolved_config)
        configured_speech_url = _resolve_baidu_file_async_speech_url(resolved_config)
        notes = [
            "Raw transcription quality comes from Baidu file-async ASR.",
        ]

        if configured_speech_url:
            speech_url = configured_speech_url
            notes.append(
                "Configured baiduFileSpeechUrl is sent directly to Baidu create/query."
            )
        else:
            try:
                upload_config = _build_cos_upload_config(
                    resolved_config,
                    url_expires_seconds=BAIDU_FILE_ASYNC_SPEECH_URL_EXPIRES_SECONDS,
                )
            except CloudTranscriptionConfigError as exc:
                raise CloudTranscriptionConfigError(
                    _build_baidu_file_async_speech_url_guidance()
                ) from exc

            with _prepare_cloud_audio_input(file_path) as audio_path:
                try:
                    speech_url = upload_audio_file(audio_path, upload_config)
                except TencentCosUploadUrlError as exc:
                    raise CloudTranscriptionApiError(str(exc)) from exc
                except TencentCosUploadError as exc:
                    raise CloudTranscriptionApiError(str(exc)) from exc

                LOGGER.info(
                    "Starting file ASR for '%s' with provider=baidu_file_async dev_pid=%s speech_url_ready=true endpoint=%s",
                    audio_path.name,
                    baidu_config.devPid,
                    BAIDU_FILE_ASYNC_CREATE_ENDPOINT,
                )

            notes.extend(
                [
                    "Video input is first converted into a compact cloud-friendly audio file before upload.",
                    "Tencent COS upload is reused to generate a temporary speech_url for Baidu create/query.",
                ]
            )

        if configured_speech_url:
            try:
                LOGGER.info(
                    "Starting file ASR for '%s' with provider=baidu_file_async dev_pid=%s speech_url_ready=true endpoint=%s",
                    file_path.name,
                    baidu_config.devPid,
                    BAIDU_FILE_ASYNC_CREATE_ENDPOINT,
                )
                pieces = transcribe_with_baidu_file_async(
                    speech_url=speech_url,
                    config=baidu_config,
                )
            except BaiduFileAsyncAsrError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc
        else:
            try:
                pieces = transcribe_with_baidu_file_async(
                    speech_url=speech_url,
                    config=baidu_config,
                )
            except BaiduFileAsyncAsrError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc

        result = _build_realtime_cloud_result(
            provider="baidu_file_async",
            model_name=baidu_config.devPid,
            endpoint_url=baidu_config.createEndpoint,
            requested_language=language,
            preprocessing_profile=OPENAI_SPEECH_PREPROCESSING_PROFILE,
            raw_pieces=pieces,
            notes=notes,
        )
        LOGGER.info(
            "Finished file ASR for '%s': provider=baidu_file_async raw_segments=%s final_segments=%s",
            file_path.name,
            result.diagnostics.rawSegmentCount,
            result.diagnostics.finalSegmentCount,
        )
        return result


class OpenAISpeechTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "openaiSpeech"
    mode = "cloud"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        resolved_config = _resolve_transcription_config(config)
        cloud_config = _resolve_cloud_transcription_config(resolved_config)

        with _prepare_cloud_audio_input(file_path) as audio_path:
            file_size = audio_path.stat().st_size
            if file_size > OPENAI_SPEECH_MAX_FILE_BYTES:
                raise CloudTranscriptionFileTooLargeError(
                    "Cloud transcription upload is too large. "
                    f"'{audio_path.name}' is {round(file_size / (1024 * 1024), 1)} MB, "
                    "but OpenAI Speech-to-Text currently accepts files up to 25 MB."
                )

            fields = [
                ("model", cloud_config.model),
                ("response_format", OPENAI_SPEECH_RESPONSE_FORMAT),
                ("timestamp_granularities[]", OPENAI_SPEECH_TIMESTAMP_GRANULARITY),
            ]
            if language:
                fields.append(("language", language))

            body, content_type = _build_multipart_form_data(
                fields=fields,
                file_field_name="file",
                file_path=audio_path,
            )

            LOGGER.info(
                "Starting cloud ASR for '%s' with provider=%s model=%s language=%s size_mb=%.2f endpoint=%s",
                audio_path.name,
                cloud_config.provider,
                cloud_config.model,
                language or "auto",
                file_size / (1024 * 1024),
                _build_openai_speech_endpoint(cloud_config.baseUrl),
            )
            response_payload = _post_cloud_transcription_request(
                url=_build_openai_speech_endpoint(cloud_config.baseUrl),
                api_key=cloud_config.apiKey,
                body=body,
                content_type=content_type,
                timeout_seconds=60,
                context_label=_build_cloud_transcription_context(cloud_config),
            )
            result = _parse_openai_cloud_segments(
                response_payload,
                requested_language=language,
                model_name=cloud_config.model,
                base_url=cloud_config.baseUrl,
            )
            LOGGER.info(
                "Finished cloud ASR for '%s': detected=%s raw_segments=%s final_segments=%s",
                audio_path.name,
                result.sourceLanguage,
                result.diagnostics.rawSegmentCount,
                result.diagnostics.finalSegmentCount,
            )
            return result


class TencentFileAsyncTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "tencent_file_async"
    mode = "cloud"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        resolved_config = _resolve_transcription_config(config)
        tencent_config = _build_tencent_file_async_config(resolved_config)
        upload_config = _build_cos_upload_config(resolved_config)

        with _prepare_cloud_audio_input(file_path) as audio_path:
            try:
                file_url = upload_audio_file(audio_path, upload_config)
            except TencentCosUploadUrlError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc
            except TencentCosUploadError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc

            LOGGER.info(
                "Starting file ASR for '%s' with provider=tencent_file_async engine_model_type=%s source_url_ready=true",
                audio_path.name,
                tencent_config.engineModelType,
            )

            try:
                pieces = transcribe_with_tencent_file_async(
                    file_url=file_url,
                    config=tencent_config,
                )
            except TencentFileAsyncAsrError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc

        result = _build_realtime_cloud_result(
            provider="tencent_file_async",
            model_name=tencent_config.engineModelType,
            endpoint_url=tencent_config.endpoint,
            requested_language=language,
            preprocessing_profile=OPENAI_SPEECH_PREPROCESSING_PROFILE,
            raw_pieces=pieces,
            notes=[
                "Raw transcription quality comes from Tencent file-async ASR.",
                "Video input is first converted into a compact cloud-friendly audio file before upload.",
                "Tencent COS upload is used to generate a temporary file_url for CreateRecTask.",
            ],
        )
        LOGGER.info(
            "Finished file ASR for '%s': provider=tencent_file_async raw_segments=%s final_segments=%s",
            file_path.name,
            result.diagnostics.rawSegmentCount,
            result.diagnostics.finalSegmentCount,
        )
        return result


class XfyunLfasrTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "xfyun_lfasr"
    mode = "cloud"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        resolved_config = _resolve_transcription_config(config)
        xfyun_config = _build_xfyun_lfasr_config(resolved_config)

        with _prepare_cloud_audio_input(file_path) as audio_path:
            LOGGER.info(
                "Starting file ASR for '%s' with provider=xfyun_lfasr endpoint=%s",
                audio_path.name,
                XFYUN_LFASR_RESULT_ENDPOINT,
            )
            try:
                pieces = transcribe_with_xfyun_lfasr(audio_path, xfyun_config)
            except XfyunLfasrError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc

        result = _build_realtime_cloud_result(
            provider="xfyun_lfasr",
            model_name="lfasr",
            endpoint_url=xfyun_config.resultEndpoint,
            requested_language=language,
            preprocessing_profile=OPENAI_SPEECH_PREPROCESSING_PROFILE,
            raw_pieces=pieces,
            notes=[
                "Raw transcription quality comes from XFYUN LFASR async ASR.",
                "Video input is first converted into a compact cloud-friendly audio file before upload.",
                "XFYUN LFASR uses the minimal prepare/upload/merge/getProgress/getResult workflow.",
            ],
        )
        LOGGER.info(
            "Finished file ASR for '%s': provider=xfyun_lfasr raw_segments=%s final_segments=%s",
            file_path.name,
            result.diagnostics.rawSegmentCount,
            result.diagnostics.finalSegmentCount,
        )
        return result


class XfyunSpeedTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "xfyun_speed_transcription"
    mode = "cloud"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        resolved_config = _resolve_transcription_config(config)
        xfyun_config = _build_xfyun_speed_config(resolved_config)

        LOGGER.info(
            "Starting file ASR for '%s' with provider=xfyun_speed_transcription endpoint=%s",
            file_path.name,
            XFYUN_SPEED_CREATE_ENDPOINT,
        )
        try:
            pieces = transcribe_with_xfyun_speed_transcription(file_path, xfyun_config)
        except XfyunSpeedTranscriptionError as exc:
            raise CloudTranscriptionApiError(str(exc)) from exc

        result = _build_realtime_cloud_result(
            provider="xfyun_speed_transcription",
            model_name="speed_transcription",
            endpoint_url=xfyun_config.queryEndpoint,
            requested_language=language,
            preprocessing_profile=XFYUN_SPEED_PREPROCESSING_PROFILE,
            raw_pieces=pieces,
            notes=[
                "Raw transcription quality comes from XFYUN speed transcription.",
                "Audio is preprocessed into mono 16 kHz 16-bit PCM WAV before upload.",
                "The provider uploads audio through XFYUN official upload endpoints, then calls pro_create/query.",
            ],
        )
        LOGGER.info(
            "Finished file ASR for '%s': provider=xfyun_speed_transcription raw_segments=%s final_segments=%s",
            file_path.name,
            result.diagnostics.rawSegmentCount,
            result.diagnostics.finalSegmentCount,
        )
        return result


class TencentRealtimeTranscriptionAdapter(TranscriptionProviderAdapter):
    provider_name = "tencent_realtime"
    mode = "cloud"

    def transcribe(
        self,
        file_path: Path,
        language: str | None,
        config: AppConfig | None,
        model_size: str,
        quality_preset: AsrQualityPreset,
    ) -> TranscriptionResult:
        resolved_config = _resolve_transcription_config(config)
        tencent_config = _build_tencent_realtime_config(resolved_config)

        LOGGER.info(
            "Starting realtime ASR for '%s' with provider=tencent_realtime engine_model_type=%s",
            file_path.name,
            tencent_config.engineModelType,
        )

        with _prepare_realtime_pcm_input(file_path, "tencent_realtime") as pcm_path:
            try:
                pieces = transcribe_with_tencent_realtime(pcm_path, tencent_config)
            except TencentRealtimeAsrError as exc:
                raise CloudTranscriptionApiError(str(exc)) from exc

        result = _build_realtime_cloud_result(
            provider="tencent_realtime",
            model_name=tencent_config.engineModelType,
            endpoint_url=tencent_config.websocketUrl,
            requested_language=language,
            preprocessing_profile=REALTIME_PCM_PREPROCESSING_PROFILE,
            raw_pieces=pieces,
            notes=[
                "Raw transcription quality comes from Tencent realtime ASR.",
                "Audio was preprocessed to mono 16 kHz pcm_s16le before websocket streaming.",
            ],
        )
        LOGGER.info(
            "Finished realtime ASR for '%s': provider=tencent_realtime raw_segments=%s final_segments=%s",
            file_path.name,
            result.diagnostics.rawSegmentCount,
            result.diagnostics.finalSegmentCount,
        )
        return result


TRANSCRIPTION_ADAPTERS: dict[SpeechProviderName, TranscriptionProviderAdapter] = {
    "baidu_realtime": BaiduRealtimeTranscriptionAdapter(),
    "baidu_file_async": BaiduFileAsyncTranscriptionAdapter(),
    "tencent_realtime": TencentRealtimeTranscriptionAdapter(),
    "tencent_file_async": TencentFileAsyncTranscriptionAdapter(),
    "xfyun_lfasr": XfyunLfasrTranscriptionAdapter(),
    "xfyun_speed_transcription": XfyunSpeedTranscriptionAdapter(),
    "openaiSpeech": OpenAISpeechTranscriptionAdapter(),
    "localFasterWhisper": LocalFasterWhisperTranscriptionAdapter(),
}


def transcribe_media(
    file_path: str | Path,
    language: AsrLanguageInput | None = None,
    model_size: str = DEFAULT_MODEL_SIZE,
    quality_preset: str = DEFAULT_QUALITY_PRESET,
    provider: str | None = None,
    config: AppConfig | None = None,
) -> TranscriptionResult:
    """Transcribe a local audio or video file into subtitle segments."""

    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise TranscriptionServiceError(f"Media file does not exist: {path}")
    if not path.is_file():
        raise TranscriptionServiceError(f"Media path is not a file: {path}")

    normalized_language = _normalize_asr_language(language)
    normalized_quality_preset = _normalize_quality_preset(quality_preset)
    resolved_config = _resolve_transcription_config(config)
    selected_provider = _resolve_selected_transcription_provider(
        resolved_config,
        provider=provider,
    )
    adapter = TRANSCRIPTION_ADAPTERS[selected_provider]

    return adapter.transcribe(
        file_path=path,
        language=normalized_language,
        config=resolved_config,
        model_size=model_size,
        quality_preset=normalized_quality_preset,
    )


def transcribeMedia(
    file_path: str | Path,
    language: AsrLanguageInput | None = None,
    model_size: str = DEFAULT_MODEL_SIZE,
    quality_preset: str = DEFAULT_QUALITY_PRESET,
    provider: str | None = None,
    config: AppConfig | None = None,
) -> TranscriptionResult:
    return transcribe_media(
        file_path=file_path,
        language=language,
        model_size=model_size,
        quality_preset=quality_preset,
        provider=provider,
        config=config,
    )


def validateSpeechConfig(
    config: AppConfig,
    timeout_seconds: int = 20,
) -> SpeechConfigValidationResult:
    return validate_speech_config(config=config, timeout_seconds=timeout_seconds)
