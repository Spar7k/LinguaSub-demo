"""File import service for LinguaSub."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .models import JsonModel, LanguageCode, MediaType, ProjectFile, ProjectState

ImportRoute = Literal["recognition", "translation"]
RecognitionMediaType = Literal["video", "audio"]

SUPPORTED_EXTENSIONS: dict[str, MediaType] = {
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".srt": "subtitle",
}

WORKFLOW_BY_TYPE: dict[MediaType, list[str]] = {
    "video": ["Video", "Recognition", "Translation", "Export"],
    "audio": ["Audio", "Recognition", "Translation", "Export"],
    "subtitle": ["SRT", "Translation", "Export"],
}


class ImportServiceError(ValueError):
    """Base error for file import problems."""


class FileNotFoundImportError(ImportServiceError):
    """Raised when the requested file does not exist."""


class UnsupportedFileTypeError(ImportServiceError):
    """Raised when the file extension is not supported."""


@dataclass(slots=True)
class RecognitionInput(JsonModel):
    mediaPath: str
    mediaType: RecognitionMediaType
    sourceLanguage: LanguageCode = "auto"


@dataclass(slots=True)
class SubtitleParseInput(JsonModel):
    subtitlePath: str
    parser: str = "srt"
    encoding: str = "auto"


@dataclass(slots=True)
class ImportResult(JsonModel):
    currentFile: ProjectFile
    projectState: ProjectState
    workflow: list[str]
    route: ImportRoute
    shouldSkipTranscription: bool
    recognitionInput: RecognitionInput | None = None
    subtitleInput: SubtitleParseInput | None = None


def normalize_import_path(raw_path: str) -> Path:
    cleaned = raw_path.strip().strip('"').strip("'")
    if not cleaned:
        raise ImportServiceError("File path is required.")

    return Path(cleaned).expanduser().resolve()


def detect_file_type(file_path: str | Path) -> MediaType:
    extension = Path(file_path).suffix.lower()
    media_type = SUPPORTED_EXTENSIONS.get(extension)

    if media_type is None:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileTypeError(
            f"Unsupported file format '{extension or 'unknown'}'. Supported formats: {supported}."
        )

    return media_type


def create_project_file(file_path: Path) -> ProjectFile:
    media_type = detect_file_type(file_path)
    return ProjectFile(
        path=str(file_path),
        name=file_path.name,
        mediaType=media_type,
        extension=file_path.suffix.lower(),
        requiresAsr=media_type in {"video", "audio"},
    )


def create_project_state_for_import(project_file: ProjectFile) -> ProjectState:
    return ProjectState(
        currentFile=project_file,
        segments=[],
        status="transcribing" if project_file.requiresAsr else "translating",
        error=None,
    )


def import_file(file_path: str) -> ImportResult:
    normalized_path = normalize_import_path(file_path)
    if not normalized_path.exists():
        raise FileNotFoundImportError(f"File does not exist: {normalized_path}")
    if not normalized_path.is_file():
        raise ImportServiceError(f"Path is not a file: {normalized_path}")

    project_file = create_project_file(normalized_path)
    project_state = create_project_state_for_import(project_file)
    workflow = WORKFLOW_BY_TYPE[project_file.mediaType]

    if project_file.mediaType == "subtitle":
        return ImportResult(
            currentFile=project_file,
            projectState=project_state,
            workflow=workflow,
            route="translation",
            shouldSkipTranscription=True,
            subtitleInput=SubtitleParseInput(subtitlePath=project_file.path),
        )

    return ImportResult(
        currentFile=project_file,
        projectState=project_state,
        workflow=workflow,
        route="recognition",
        shouldSkipTranscription=False,
        recognitionInput=RecognitionInput(
            mediaPath=project_file.path,
            mediaType=project_file.mediaType,
        ),
    )


def importFile(file_path: str) -> ImportResult:
    return import_file(file_path)
