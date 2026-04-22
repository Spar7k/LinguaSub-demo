"""Core data structures used by LinguaSub."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

LanguageCode = Literal["auto", "zh-CN", "en", "ja", "ko"]
ProviderName = Literal["openaiCompatible", "deepseek"]
TranscriptionProviderName = Literal[
    "baidu_realtime",
    "tencent_realtime",
    "openaiSpeech",
    "localFasterWhisper",
]
FileAsyncTranscriptionProviderName = Literal[
    "baidu_file_async",
    "tencent_file_async",
    "xfyun_lfasr",
    "xfyun_speed_transcription",
]
SpeechProviderName = Literal[
    "baidu_realtime",
    "tencent_realtime",
    "openaiSpeech",
    "localFasterWhisper",
    "baidu_file_async",
    "tencent_file_async",
    "xfyun_lfasr",
    "xfyun_speed_transcription",
]
OutputMode = Literal["bilingual", "single"]
TranslationTaskStatus = Literal["queued", "translating", "done", "error"]
ProjectStatus = Literal["idle", "transcribing", "translating", "exporting", "done", "error"]
MediaType = Literal["video", "audio", "subtitle"]


class JsonModel:
    """Small helper that keeps every model easy to save as JSON."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProjectFile(JsonModel):
    path: str
    name: str
    mediaType: MediaType
    extension: str
    requiresAsr: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectFile":
        return cls(
            path=data["path"],
            name=data["name"],
            mediaType=data["mediaType"],
            extension=data["extension"],
            requiresAsr=data["requiresAsr"],
        )


@dataclass(slots=True)
class SubtitleSegment(JsonModel):
    id: str
    start: int
    end: int
    sourceText: str
    translatedText: str
    sourceLanguage: LanguageCode
    targetLanguage: LanguageCode

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubtitleSegment":
        return cls(
            id=data["id"],
            start=int(data["start"]),
            end=int(data["end"]),
            sourceText=data["sourceText"],
            translatedText=data["translatedText"],
            sourceLanguage=data["sourceLanguage"],
            targetLanguage=data["targetLanguage"],
        )


@dataclass(slots=True)
class ApiProviderConfig(JsonModel):
    provider: ProviderName
    displayName: str
    apiKey: str
    baseUrl: str
    model: str
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApiProviderConfig":
        return cls(
            provider=data["provider"],
            displayName=data["displayName"],
            apiKey=data["apiKey"],
            baseUrl=data["baseUrl"],
            model=data["model"],
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(slots=True)
class AppConfig(JsonModel):
    apiProviders: list[ApiProviderConfig] = field(default_factory=list)
    defaultProvider: ProviderName = "openaiCompatible"
    defaultTranscriptionProvider: SpeechProviderName = "baidu_realtime"
    speechProvider: SpeechProviderName = "baidu_realtime"
    # These mirror the active provider so the UI can edit one flat object.
    apiKey: str = ""
    baseUrl: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    speechApiKey: str = ""
    speechBaseUrl: str = "https://api.openai.com/v1"
    speechModel: str = "whisper-1"
    baiduAppId: str = ""
    baiduApiKey: str = ""
    baiduDevPid: str = "15372"
    baiduCuid: str = "linguasub-desktop"
    baiduFileAppId: str = ""
    baiduFileApiKey: str = ""
    baiduFileSecretKey: str = ""
    baiduFileDevPid: str = "15372"
    baiduFileSpeechUrl: str = ""
    tencentAppId: str = ""
    tencentSecretId: str = ""
    tencentSecretKey: str = ""
    tencentEngineModelType: str = "16k_zh"
    tencentFileSecretId: str = ""
    tencentFileSecretKey: str = ""
    tencentFileEngineModelType: str = "16k_zh"
    xfyunAppId: str = ""
    xfyunSecretKey: str = ""
    xfyunSpeedAppId: str = ""
    xfyunSpeedApiKey: str = ""
    xfyunSpeedApiSecret: str = ""
    uploadCosSecretId: str = ""
    uploadCosSecretKey: str = ""
    uploadCosBucket: str = ""
    uploadCosRegion: str = ""
    outputMode: OutputMode = "bilingual"
    modelStoragePath: str = ""
    managedModelRoots: list[str] = field(default_factory=list)
    managedModelPaths: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        raw_provider = data.get(
            "speechProvider",
            data.get("defaultTranscriptionProvider", "baidu_realtime"),
        )

        return cls(
            apiProviders=[
                ApiProviderConfig.from_dict(item)
                for item in data.get("apiProviders", [])
            ],
            defaultProvider=data.get("defaultProvider", "openaiCompatible"),
            defaultTranscriptionProvider=raw_provider,
            speechProvider=raw_provider,
            apiKey=data.get("apiKey", ""),
            baseUrl=data.get("baseUrl", "https://api.openai.com/v1"),
            model=data.get("model", "gpt-4.1-mini"),
            speechApiKey=data.get("speechApiKey", ""),
            speechBaseUrl=data.get("speechBaseUrl", "https://api.openai.com/v1"),
            speechModel=data.get("speechModel", "whisper-1"),
            baiduAppId=data.get("baiduAppId", ""),
            baiduApiKey=data.get("baiduApiKey", ""),
            baiduDevPid=str(data.get("baiduDevPid", "15372") or "15372"),
            baiduCuid=data.get("baiduCuid", "linguasub-desktop"),
            baiduFileAppId=data.get("baiduFileAppId", ""),
            baiduFileApiKey=data.get("baiduFileApiKey", ""),
            baiduFileSecretKey=data.get("baiduFileSecretKey", ""),
            baiduFileDevPid=str(data.get("baiduFileDevPid", "15372") or "15372"),
            baiduFileSpeechUrl=data.get("baiduFileSpeechUrl", ""),
            tencentAppId=data.get("tencentAppId", ""),
            tencentSecretId=data.get("tencentSecretId", ""),
            tencentSecretKey=data.get("tencentSecretKey", ""),
            tencentEngineModelType=data.get(
                "tencentEngineModelType", "16k_zh"
            ),
            tencentFileSecretId=data.get("tencentFileSecretId", ""),
            tencentFileSecretKey=data.get("tencentFileSecretKey", ""),
            tencentFileEngineModelType=data.get(
                "tencentFileEngineModelType", "16k_zh"
            ),
            xfyunAppId=data.get("xfyunAppId", ""),
            xfyunSecretKey=data.get("xfyunSecretKey", ""),
            xfyunSpeedAppId=data.get("xfyunSpeedAppId", ""),
            xfyunSpeedApiKey=data.get("xfyunSpeedApiKey", ""),
            xfyunSpeedApiSecret=data.get("xfyunSpeedApiSecret", ""),
            uploadCosSecretId=data.get("uploadCosSecretId", ""),
            uploadCosSecretKey=data.get("uploadCosSecretKey", ""),
            uploadCosBucket=data.get("uploadCosBucket", ""),
            uploadCosRegion=data.get("uploadCosRegion", ""),
            outputMode=data.get("outputMode", "bilingual"),
            modelStoragePath=data.get("modelStoragePath", ""),
            managedModelRoots=[
                str(item).strip()
                for item in data.get("managedModelRoots", [])
                if str(item).strip()
            ],
            managedModelPaths=[
                str(item).strip()
                for item in data.get("managedModelPaths", [])
                if str(item).strip()
            ],
        )


@dataclass(slots=True)
class TranslationTask(JsonModel):
    provider: ProviderName
    model: str
    sourceLanguage: LanguageCode
    targetLanguage: LanguageCode
    segments: list[SubtitleSegment] = field(default_factory=list)
    status: TranslationTaskStatus = "queued"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranslationTask":
        return cls(
            provider=data["provider"],
            model=data["model"],
            sourceLanguage=data["sourceLanguage"],
            targetLanguage=data["targetLanguage"],
            segments=[
                SubtitleSegment.from_dict(item) for item in data.get("segments", [])
            ],
            status=data.get("status", "queued"),
        )


@dataclass(slots=True)
class ProjectState(JsonModel):
    currentFile: ProjectFile | None = None
    segments: list[SubtitleSegment] = field(default_factory=list)
    status: ProjectStatus = "idle"
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        current_file_data = data.get("currentFile")

        return cls(
            currentFile=(
                ProjectFile.from_dict(current_file_data) if current_file_data else None
            ),
            segments=[
                SubtitleSegment.from_dict(item) for item in data.get("segments", [])
            ],
            status=data.get("status", "idle"),
            error=data.get("error"),
        )


def create_default_app_config() -> AppConfig:
    return AppConfig(
        apiProviders=[
            ApiProviderConfig(
                provider="openaiCompatible",
                displayName="OpenAI Compatible",
                apiKey="",
                baseUrl="https://api.openai.com/v1",
                model="gpt-4.1-mini",
                enabled=True,
            ),
            ApiProviderConfig(
                provider="deepseek",
                displayName="DeepSeek",
                apiKey="",
                baseUrl="https://api.deepseek.com/v1",
                model="deepseek-chat",
                enabled=True,
            ),
        ],
        defaultProvider="openaiCompatible",
        defaultTranscriptionProvider="baidu_realtime",
        speechProvider="baidu_realtime",
        apiKey="",
        baseUrl="https://api.openai.com/v1",
        model="gpt-4.1-mini",
        speechApiKey="",
        speechBaseUrl="https://api.openai.com/v1",
        speechModel="whisper-1",
        baiduAppId="",
        baiduApiKey="",
        baiduDevPid="15372",
        baiduCuid="linguasub-desktop",
        baiduFileAppId="",
        baiduFileApiKey="",
        baiduFileSecretKey="",
        baiduFileDevPid="15372",
        baiduFileSpeechUrl="",
        tencentAppId="",
        tencentSecretId="",
        tencentSecretKey="",
        tencentEngineModelType="16k_zh",
        tencentFileSecretId="",
        tencentFileSecretKey="",
        tencentFileEngineModelType="16k_zh",
        xfyunAppId="",
        xfyunSecretKey="",
        xfyunSpeedAppId="",
        xfyunSpeedApiKey="",
        xfyunSpeedApiSecret="",
        uploadCosSecretId="",
        uploadCosSecretKey="",
        uploadCosBucket="",
        uploadCosRegion="",
        outputMode="bilingual",
        modelStoragePath="",
        managedModelRoots=[],
        managedModelPaths=[],
    )


def create_empty_project_state() -> ProjectState:
    return ProjectState(currentFile=None, segments=[], status="idle", error=None)
