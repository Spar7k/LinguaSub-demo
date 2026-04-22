"""Environment and first-run checks for Windows packaging guidance."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Literal

from .config_service import (
    get_config_path,
    get_default_user_data_dir,
    get_recommended_release_config_path,
    load_config,
)
from .models import JsonModel
from .speech_runtime_service import (
    DEFAULT_ASR_MODEL_SIZE,
    build_speech_model_statuses,
    get_download_status,
    get_default_model_storage_dir,
    get_faster_whisper_runtime_status,
    get_model_storage_dir,
    resolve_ffmpeg_binary,
    SpeechModelDownloadStatus,
    SpeechModelStatus,
)
from .models import AppConfig

RuntimeMode = Literal["development", "release"]


@dataclass(slots=True)
class DependencyStatus(JsonModel):
    key: str
    label: str
    available: bool
    requiredFor: str
    detectedPath: str | None = None
    installHint: str = ""
    details: str = ""


@dataclass(slots=True)
class StartupCheckReport(JsonModel):
    mode: RuntimeMode
    backendReachable: bool
    pythonExecutable: str
    currentConfigPath: str
    recommendedConfigPath: str
    userDataDir: str
    defaultSpeechModelStorageDir: str
    speechModelStorageDir: str
    defaultProvider: str
    defaultTranscriptionProvider: str
    defaultModel: str
    speechBaseUrl: str
    speechModel: str
    defaultAsrModelSize: str
    outputMode: str
    apiKeyConfigured: bool
    speechApiConfigured: bool
    readyForSrtWorkflow: bool
    readyForMediaWorkflow: bool
    readyForCloudTranscription: bool
    readyForLocalTranscription: bool
    exportRule: str
    dependencies: list[DependencyStatus] = field(default_factory=list)
    speechModels: list[SpeechModelStatus] = field(default_factory=list)
    activeModelDownload: SpeechModelDownloadStatus = field(
        default_factory=SpeechModelDownloadStatus
    )
    warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def detect_runtime_mode() -> RuntimeMode:
    if getattr(sys, "frozen", False):
        return "release"

    return "development"


def _check_backend() -> DependencyStatus:
    return DependencyStatus(
        key="backend",
        label="LinguaSub backend",
        available=True,
        requiredFor="Environment checks and local workflow orchestration",
        detectedPath=sys.executable,
        installHint="The packaged backend should start automatically when LinguaSub launches.",
        details=(
            "This report is returned by the local backend, so backendReachable means "
            "the bundled sidecar is already answering requests."
        ),
    )


def _check_ffmpeg() -> DependencyStatus:
    ffmpeg_path = resolve_ffmpeg_binary()
    return DependencyStatus(
        key="ffmpeg",
        label="FFmpeg",
        available=ffmpeg_path is not None,
        requiredFor="Video and audio recognition",
        detectedPath=str(ffmpeg_path) if ffmpeg_path else None,
        installHint=(
            "Bundle ffmpeg.exe inside src-tauri/resources/runtime/ffmpeg so the "
            "packaged app can resolve it automatically."
        ),
        details="LinguaSub uses FFmpeg to extract audio from video files before ASR.",
    )


def _check_faster_whisper_runtime() -> DependencyStatus:
    runtime_status = get_faster_whisper_runtime_status()
    return DependencyStatus(
        key="fasterWhisperRuntime",
        label="faster-whisper runtime",
        available=runtime_status.available,
        requiredFor="Local speech recognition",
        detectedPath=runtime_status.detectedPath,
        installHint=(
            "Package the backend sidecar with faster-whisper, ctranslate2, tokenizers, "
            "and their runtime libraries included."
        ),
        details=runtime_status.details
        or "LinguaSub uses faster-whisper for local subtitle generation from media files.",
    )


def _check_cloud_transcription_config(config: AppConfig) -> DependencyStatus:
    provider = config.speechProvider or config.defaultTranscriptionProvider
    if provider == "baidu_realtime":
        speech_ready = bool(
            config.baiduAppId.strip()
            and config.baiduApiKey.strip()
            and config.baiduDevPid.strip()
            and config.baiduCuid.strip()
        )
        detected_path = "wss://vop.baidu.com/realtime_asr"
        install_hint = "打开设置页，填写百度 AppID、百度 API Key、百度识别模型 PID 和 CUID。"
        details = "LinguaSub uses Baidu realtime websocket ASR for the recommended media recognition route."
    elif provider == "tencent_realtime":
        speech_ready = bool(
            config.tencentAppId.strip()
            and config.tencentSecretId.strip()
            and config.tencentSecretKey.strip()
            and config.tencentEngineModelType.strip()
        )
        detected_path = (
            f"wss://asr.cloud.tencent.com/asr/v2/{config.tencentAppId.strip()}"
            if config.tencentAppId.strip()
            else None
        )
        install_hint = "打开设置页，填写腾讯 AppID、SecretID、SecretKey 和引擎模型类型。"
        details = "LinguaSub keeps a Tencent realtime ASR provider slot for future websocket integration."
    else:
        speech_ready = bool(
            config.speechApiKey.strip()
            and config.speechBaseUrl.strip()
            and config.speechModel.strip()
        )
        detected_path = config.speechBaseUrl.strip() or None
        install_hint = (
            "Open Settings and save the OpenAI Speech-to-Text base URL, API key, and model."
        )
        details = (
            "LinguaSub uses the saved cloud transcription API configuration for the recommended media recognition route."
        )

    return DependencyStatus(
        key="cloudTranscriptionConfig",
        label="Cloud transcription",
        available=speech_ready,
        requiredFor="Cloud speech recognition (recommended)",
        detectedPath=detected_path,
        installHint=install_hint,
        details=details,
    )


def build_startup_check() -> StartupCheckReport:
    config = load_config()
    current_config_path = get_config_path().resolve()
    recommended_config_path = get_recommended_release_config_path().resolve()
    user_data_dir = get_default_user_data_dir().resolve()
    default_speech_model_storage_dir = get_default_model_storage_dir().resolve()
    speech_model_storage_dir = get_model_storage_dir().resolve()
    dependencies = [
        _check_backend(),
        _check_cloud_transcription_config(config),
        _check_ffmpeg(),
        _check_faster_whisper_runtime(),
    ]
    speech_models = build_speech_model_statuses()
    active_model_download = get_download_status()

    cloud_transcription_status = next(
        item for item in dependencies if item.key == "cloudTranscriptionConfig"
    )
    ffmpeg_status = next(item for item in dependencies if item.key == "ffmpeg")
    whisper_runtime_status = next(
        item for item in dependencies if item.key == "fasterWhisperRuntime"
    )

    api_key_configured = bool(config.apiKey.strip())
    speech_provider = config.speechProvider or config.defaultTranscriptionProvider
    if speech_provider == "baidu_realtime":
        speech_api_configured = bool(config.baiduApiKey.strip())
        speech_base_url = "wss://vop.baidu.com/realtime_asr"
        speech_model = config.baiduDevPid.strip() or "15372"
    elif speech_provider == "tencent_realtime":
        speech_api_configured = bool(config.tencentSecretId.strip() and config.tencentSecretKey.strip())
        speech_base_url = (
            f"wss://asr.cloud.tencent.com/asr/v2/{config.tencentAppId.strip()}"
            if config.tencentAppId.strip()
            else "wss://asr.cloud.tencent.com/asr/v2/<appid>"
        )
        speech_model = config.tencentEngineModelType.strip() or "16k_zh"
    elif speech_provider == "localFasterWhisper":
        speech_api_configured = True
        speech_base_url = "local://faster-whisper"
        speech_model = DEFAULT_ASR_MODEL_SIZE
    else:
        speech_api_configured = bool(config.speechApiKey.strip())
        speech_base_url = config.speechBaseUrl
        speech_model = config.speechModel
    ready_for_srt_workflow = True
    ready_for_cloud_transcription = cloud_transcription_status.available
    ready_for_local_transcription = (
        ffmpeg_status.available
        and whisper_runtime_status.available
        and any(model.available for model in speech_models)
    )
    ready_for_media_workflow = (
        ready_for_cloud_transcription or ready_for_local_transcription
    )

    warnings: list[str] = []
    actions: list[str] = []

    if (
        speech_provider != "localFasterWhisper"
        and not cloud_transcription_status.available
    ):
        warnings.append(
            "Cloud transcription is not configured yet. Add the OpenAI Speech-to-Text API key before using the recommended media recognition route."
        )
        actions.append(cloud_transcription_status.installHint)

    if not api_key_configured:
        warnings.append(
            "The active translation provider does not have an API key yet. Translation requests will fail until one is configured."
        )
        actions.append(
            "Open Translation Setup or Settings and save the API key for the default provider."
        )

    if speech_provider == "localFasterWhisper" and not ffmpeg_status.available:
        warnings.append(
            "FFmpeg is missing. Video and audio files cannot enter the local recognition route yet."
        )
        actions.append(ffmpeg_status.installHint)

    if (
        speech_provider == "localFasterWhisper"
        and not whisper_runtime_status.available
    ):
        warnings.append(
            "The faster-whisper runtime is missing. Media transcription cannot run until the bundled backend includes the runtime."
        )
        actions.append(whisper_runtime_status.installHint)

    if (
        speech_provider == "localFasterWhisper"
        and whisper_runtime_status.available
        and not any(model.available for model in speech_models)
    ):
        warnings.append(
            "No speech model files are installed yet. Download tiny, base, or small before starting media recognition."
        )
        actions.append(
            "Use the Download Model action in the Import page. LinguaSub saves model files to the default speech model folder under user data."
        )

    if active_model_download.active:
        actions.append(active_model_download.message)

    if current_config_path != recommended_config_path:
        actions.append(
            "For Windows release builds, keep LINGUASUB_CONFIG_PATH in the user data folder so config does not live inside the app install directory."
        )

    return StartupCheckReport(
        mode=detect_runtime_mode(),
        backendReachable=True,
        pythonExecutable=sys.executable,
        currentConfigPath=str(current_config_path),
        recommendedConfigPath=str(recommended_config_path),
        userDataDir=str(user_data_dir),
        defaultSpeechModelStorageDir=str(default_speech_model_storage_dir),
        speechModelStorageDir=str(speech_model_storage_dir),
        defaultProvider=config.defaultProvider,
        defaultTranscriptionProvider=speech_provider,
        defaultModel=config.model,
        speechBaseUrl=speech_base_url,
        speechModel=speech_model,
        defaultAsrModelSize=DEFAULT_ASR_MODEL_SIZE,
        outputMode=config.outputMode,
        apiKeyConfigured=api_key_configured,
        speechApiConfigured=speech_api_configured,
        readyForSrtWorkflow=ready_for_srt_workflow,
        readyForMediaWorkflow=ready_for_media_workflow,
        readyForCloudTranscription=ready_for_cloud_transcription,
        readyForLocalTranscription=ready_for_local_transcription,
        exportRule=(
            "Exported files are saved beside the imported source file by default. "
            "SRT exports use <source>.bilingual.srt or <source>.single.srt, and Word exports use "
            "<source>_bilingual.docx or <source>_transcript.docx when no custom name is provided."
        ),
        dependencies=dependencies,
        speechModels=speech_models,
        activeModelDownload=active_model_download,
        warnings=warnings,
        actions=actions,
    )


buildStartupCheck = build_startup_check
