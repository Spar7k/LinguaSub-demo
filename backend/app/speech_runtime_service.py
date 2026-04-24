"""Runtime and first-use model management for local speech recognition."""

from __future__ import annotations

import importlib
import inspect
import json
import os
import shutil
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .config_service import (
    get_default_user_data_dir,
    load_config,
    save_config,
)
from .models import JsonModel

AsrModelSize = Literal["tiny", "base", "small"]
SpeechModelState = Literal["ready", "missing", "downloading", "error", "unavailable"]
SpeechModelDownloadState = Literal["idle", "starting", "downloading", "done", "error"]

SUPPORTED_ASR_MODEL_SIZES: tuple[AsrModelSize, ...] = ("tiny", "base", "small")
DEFAULT_ASR_MODEL_SIZE: AsrModelSize = "small"
MODEL_REGISTRY_FILE_NAME = "model-registry.json"
MODEL_ROOT_MARKER_FILE_NAME = ".linguasub-model-root.json"
MODEL_STORAGE_ENV = "LINGUASUB_MODEL_DIR"
RUNTIME_DIR_ENV = "LINGUASUB_RUNTIME_DIR"
FFMPEG_PATH_ENV = "LINGUASUB_FFMPEG_PATH"
FFPROBE_PATH_ENV = "LINGUASUB_FFPROBE_PATH"
CUSTOM_MODEL_ROOT_FOLDER_NAME = "LinguaSub"
CUSTOM_MODEL_ROOT_MODELS_FOLDER_NAME = "Models"
MODEL_ROOT_MARKER_SCHEMA = "linguasub/speech-model-root/v1"
MODEL_REGISTRY_SCHEMA = "linguasub/speech-model-manifest/v1"
LINGUASUB_APP_ID = "com.linguasub.desktop"
MIN_FREE_SPACE_BYTES: dict[AsrModelSize, int] = {
    "tiny": 800 * 1024 * 1024,
    "base": 1_500 * 1024 * 1024,
    "small": 3_000 * 1024 * 1024,
}
REQUIRED_MODEL_FILES = ("config.json", "model.bin")
TOKENIZER_MARKERS = ("tokenizer.json", "vocabulary.json", "tokenizer_config.json")


class SpeechRuntimeError(RuntimeError):
    """Base error for bundled ASR runtime management."""


class FasterWhisperRuntimeUnavailableError(SpeechRuntimeError):
    """Raised when faster-whisper runtime files are not available."""


class SpeechModelNotDownloadedError(SpeechRuntimeError):
    """Raised when the chosen speech model is not installed locally yet."""


class SpeechModelDownloadConflictError(SpeechRuntimeError):
    """Raised when a new model download is requested while another is active."""


class SpeechModelDownloadFailedError(SpeechRuntimeError):
    """Raised when LinguaSub cannot download the speech model."""


class SpeechModelStorageValidationError(SpeechRuntimeError):
    """Raised when the chosen model storage directory is invalid."""


class SpeechModelCleanupError(SpeechRuntimeError):
    """Raised when LinguaSub cannot safely clean up downloaded models."""


@dataclass(slots=True)
class FasterWhisperRuntimeStatus(JsonModel):
    available: bool
    detectedPath: str | None = None
    details: str = ""


@dataclass(slots=True)
class SpeechModelStatus(JsonModel):
    size: AsrModelSize
    label: str
    available: bool
    status: SpeechModelState
    detectedPath: str | None = None
    statusText: str = ""
    details: str = ""
    actionHint: str = ""


@dataclass(slots=True)
class ModelStorageValidationResult(JsonModel):
    path: str
    usingDefaultStorage: bool
    createdDirectory: bool
    writable: bool
    freeSpaceBytes: int | None = None
    recommendedFreeSpaceBytes: int | None = None


@dataclass(slots=True)
class SpeechModelDownloadStatus(JsonModel):
    active: bool = False
    modelSize: AsrModelSize | None = None
    status: SpeechModelDownloadState = "idle"
    targetPath: str | None = None
    usingDefaultStorage: bool = True
    progress: int = 0
    message: str = ""
    error: str | None = None


@dataclass(slots=True)
class SpeechModelCleanupResult(JsonModel):
    removedModelPaths: list[str] = field(default_factory=list)
    removedRootPaths: list[str] = field(default_factory=list)
    removedMetadataPaths: list[str] = field(default_factory=list)
    skippedPaths: list[str] = field(default_factory=list)
    protectedPaths: list[str] = field(default_factory=list)
    message: str = ""


_download_lock = threading.Lock()
_download_status = SpeechModelDownloadStatus()


def normalize_asr_model_size(model_size: str | None) -> AsrModelSize:
    normalized = (model_size or DEFAULT_ASR_MODEL_SIZE).strip().lower()
    if normalized not in SUPPORTED_ASR_MODEL_SIZES:
        supported = ", ".join(SUPPORTED_ASR_MODEL_SIZES)
        raise SpeechRuntimeError(
            f"Unsupported speech model size '{model_size}'. Use one of: {supported}."
        )

    return normalized  # type: ignore[return-value]


def get_runtime_root() -> Path | None:
    for candidate in _iter_runtime_root_candidates():
        if candidate.exists():
            return candidate.resolve()

    return None


def _iter_runtime_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    configured_root = os.getenv(RUNTIME_DIR_ENV)
    if configured_root:
        candidates.append(Path(configured_root).expanduser().resolve())

    try:
        current_working_dir = Path.cwd().resolve()
        candidates.append((current_working_dir / "resources" / "runtime").resolve())
        candidates.append((current_working_dir / "runtime").resolve())
    except Exception:
        pass

    try:
        launch_path = Path(sys.argv[0]).expanduser().resolve()
        launch_dir = launch_path.parent
        candidates.append((launch_dir / "resources" / "runtime").resolve())
        candidates.append((launch_dir / "runtime").resolve())
    except Exception:
        pass

    try:
        executable_dir = Path(sys.executable).expanduser().resolve().parent
    except Exception:
        executable_dir = None

    if executable_dir is not None:
        candidates.append((executable_dir / "resources" / "runtime").resolve())
        candidates.append((executable_dir / "runtime").resolve())

    deduped_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped_candidates.append(candidate)

    return deduped_candidates


def get_default_model_storage_dir() -> Path:
    return get_default_user_data_dir() / "speech-models"


def _is_link_like_path(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True

    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if bool(is_junction()):
                return True
        except OSError:
            return True

    return False


def _has_link_like_segment(path: Path, stop_at: Path | None = None) -> bool:
    current = path.expanduser()
    stop_target = stop_at.expanduser() if stop_at is not None else None

    while True:
        if current.exists() and _is_link_like_path(current):
            return True
        if stop_target is not None and current == stop_target:
            break

        parent = current.parent
        if parent == current:
            break
        current = parent

    return False


def _looks_like_custom_owned_root(path: Path) -> bool:
    return (
        path.name.casefold() == CUSTOM_MODEL_ROOT_MODELS_FOLDER_NAME.casefold()
        and path.parent.name.casefold() == CUSTOM_MODEL_ROOT_FOLDER_NAME.casefold()
    )


def _resolve_storage_root_from_selection(storage_path: str | Path | None) -> tuple[Path, bool]:
    if storage_path is None:
        return get_default_model_storage_dir().resolve(), True

    selected_path = Path(storage_path).expanduser().resolve()
    if _looks_like_custom_owned_root(selected_path):
        return selected_path, False

    return (
        selected_path / CUSTOM_MODEL_ROOT_FOLDER_NAME / CUSTOM_MODEL_ROOT_MODELS_FOLDER_NAME
    ).resolve(), False


def get_saved_model_storage_path() -> Path | None:
    try:
        config = load_config()
    except Exception:
        return None

    configured_path = config.modelStoragePath.strip()
    if not configured_path:
        return None

    return Path(configured_path).expanduser().resolve()


def get_model_storage_dir() -> Path:
    saved_path = get_saved_model_storage_path()
    if saved_path is not None:
        return saved_path

    configured_root = os.getenv(MODEL_STORAGE_ENV)
    if configured_root:
        return Path(configured_root).expanduser().resolve()

    return get_default_model_storage_dir().resolve()


def get_model_root_marker_path(root_path: str | Path | None = None) -> Path:
    root = get_model_storage_dir() if root_path is None else Path(root_path).expanduser().resolve()
    return root / MODEL_ROOT_MARKER_FILE_NAME


def get_model_registry_path(root_path: str | Path | None = None) -> Path:
    root = get_model_storage_dir() if root_path is None else Path(root_path).expanduser().resolve()
    return root / MODEL_REGISTRY_FILE_NAME


def _read_model_root_marker(root_path: str | Path) -> dict[str, Any] | None:
    marker_path = get_model_root_marker_path(root_path)
    if not marker_path.exists():
        return None

    try:
        with marker_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    return data


def _is_owned_model_root(root_path: str | Path) -> bool:
    root = Path(root_path).expanduser().resolve()
    marker = _read_model_root_marker(root)
    if not marker:
        return False

    return (
        marker.get("schema") in (None, MODEL_ROOT_MARKER_SCHEMA)
        and marker.get("app") == "LinguaSub"
        and marker.get("appId") in (None, LINGUASUB_APP_ID)
        and marker.get("kind") == "speech-model-root"
        and marker.get("rootPath") == str(root)
        and marker.get("manifestFile") == MODEL_REGISTRY_FILE_NAME
    )


def ensure_model_root_metadata(
    root_path: str | Path,
    *,
    using_default_storage: bool,
) -> None:
    root = Path(root_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    marker_payload = {
        "schema": MODEL_ROOT_MARKER_SCHEMA,
        "version": 1,
        "app": "LinguaSub",
        "appId": LINGUASUB_APP_ID,
        "kind": "speech-model-root",
        "rootPath": str(root),
        "storageKind": "default" if using_default_storage else "custom",
        "manifestFile": MODEL_REGISTRY_FILE_NAME,
    }
    marker_path = get_model_root_marker_path(root)
    with marker_path.open("w", encoding="utf-8") as file:
        json.dump(marker_payload, file, ensure_ascii=False, indent=2)

    registry_path = get_model_registry_path(root)
    if not registry_path.exists():
        with registry_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "schema": MODEL_REGISTRY_SCHEMA,
                    "version": 1,
                    "app": "LinguaSub",
                    "appId": LINGUASUB_APP_ID,
                    "kind": "speech-model-manifest",
                    "rootPath": str(root),
                    "modelPaths": {},
                },
                file,
                ensure_ascii=False,
                indent=2,
            )


def ensure_model_storage_dir(storage_path: str | Path | None = None) -> Path:
    model_dir, using_default_storage = _resolve_storage_root_from_selection(storage_path)
    model_dir.mkdir(parents=True, exist_ok=True)
    ensure_model_root_metadata(
        model_dir,
        using_default_storage=using_default_storage,
    )
    return model_dir


def persist_model_storage_preference(storage_path: str | Path | None) -> None:
    config = load_config()
    config.modelStoragePath = (
        str(_resolve_storage_root_from_selection(storage_path)[0]) if storage_path else ""
    )
    save_config(config)


def _normalize_manifest_paths(data: Any, root_path: Path) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}

    legacy_entries = {
        key: value
        for key, value in data.items()
        if key in SUPPORTED_ASR_MODEL_SIZES and isinstance(value, str) and value.strip()
    }
    if legacy_entries:
        return legacy_entries

    model_paths = data.get("modelPaths")
    if not isinstance(model_paths, dict):
        return {}

    cleaned: dict[str, str] = {}
    for key, value in model_paths.items():
        if key in SUPPORTED_ASR_MODEL_SIZES and isinstance(value, str) and value.strip():
            resolved_value = str(Path(value).expanduser().resolve())
            if Path(resolved_value).is_relative_to(root_path):
                cleaned[key] = resolved_value

    return cleaned


def _load_model_registry(root_path: str | Path | None = None) -> dict[str, str]:
    root = get_model_storage_dir() if root_path is None else Path(root_path).expanduser().resolve()
    registry_path = get_model_registry_path(root)
    if not registry_path.exists():
        return {}

    try:
        with registry_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return _normalize_manifest_paths(data, root)


def _save_model_registry(
    registry: dict[str, str],
    root_path: str | Path | None = None,
) -> None:
    root = get_model_storage_dir() if root_path is None else Path(root_path).expanduser().resolve()
    ensure_model_root_metadata(root, using_default_storage=root == get_default_model_storage_dir().resolve())
    registry_path = get_model_registry_path(root)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "schema": MODEL_REGISTRY_SCHEMA,
                "version": 1,
                "app": "LinguaSub",
                "appId": LINGUASUB_APP_ID,
                "kind": "speech-model-manifest",
                "rootPath": str(root),
                "modelPaths": registry,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )


def _record_managed_model_path(model_path: Path) -> None:
    config = load_config()
    normalized_path = str(model_path.expanduser().resolve())
    existing_paths = {
        str(Path(item).expanduser().resolve())
        for item in config.managedModelPaths
        if str(item).strip()
    }
    if normalized_path not in existing_paths:
        config.managedModelPaths.append(normalized_path)
        save_config(config)


def _record_managed_model_root(root_path: Path) -> None:
    config = load_config()
    normalized_root = str(root_path.expanduser().resolve())
    existing_roots = {
        str(Path(item).expanduser().resolve())
        for item in config.managedModelRoots
        if str(item).strip()
    }
    if normalized_root not in existing_roots:
        config.managedModelRoots.append(normalized_root)
        save_config(config)


def _remove_managed_references(model_paths: list[Path], root_paths: list[Path]) -> None:
    normalized_model_targets = {str(path.expanduser().resolve()) for path in model_paths}
    normalized_root_targets = {str(path.expanduser().resolve()) for path in root_paths}
    if not normalized_model_targets and not normalized_root_targets:
        return

    config = load_config()
    config.managedModelPaths = [
        str(Path(item).expanduser().resolve())
        for item in config.managedModelPaths
        if str(item).strip()
        and str(Path(item).expanduser().resolve()) not in normalized_model_targets
    ]
    config.managedModelRoots = [
        str(Path(item).expanduser().resolve())
        for item in config.managedModelRoots
        if str(item).strip()
        and str(Path(item).expanduser().resolve()) not in normalized_root_targets
    ]
    save_config(config)


def register_model_path(model_size: str, model_path: str | Path) -> Path:
    normalized_model_size = normalize_asr_model_size(model_size)
    resolved_path = Path(model_path).expanduser().resolve()
    current_storage_root = get_model_storage_dir().resolve()
    try:
        resolved_path.relative_to(current_storage_root)
        root = current_storage_root
    except ValueError:
        root = resolved_path.parent.resolve()
    ensure_model_root_metadata(
        root,
        using_default_storage=root == get_default_model_storage_dir().resolve(),
    )
    registry = _load_model_registry(root)
    registry[normalized_model_size] = str(resolved_path)
    _save_model_registry(registry, root)
    _record_managed_model_root(root)
    _record_managed_model_path(resolved_path)
    return resolved_path


def _get_missing_model_files(path: Path) -> list[str]:
    if not path.exists() or not path.is_dir():
        return ["directory"]

    missing_files = [file_name for file_name in REQUIRED_MODEL_FILES if not (path / file_name).exists()]
    tokenizer_available = any((path / marker).exists() for marker in TOKENIZER_MARKERS)
    if not tokenizer_available:
        missing_files.append("tokenizer")

    return missing_files


def verify_model_directory(path: str | Path) -> tuple[bool, list[str]]:
    resolved_path = Path(path).expanduser().resolve()
    missing_files = _get_missing_model_files(resolved_path)
    return len(missing_files) == 0, missing_files


def _looks_like_model_directory(path: Path) -> bool:
    is_valid, _ = verify_model_directory(path)
    return is_valid


def _format_bytes(value: int) -> str:
    gib = 1024 * 1024 * 1024
    mib = 1024 * 1024
    if value >= gib:
        return f"{value / gib:.1f} GB"
    return f"{value / mib:.0f} MB"


def _log_model_download(message: str) -> None:
    print(f"[LinguaSub][Models] {message}")


def validate_model_storage_directory(
    model_size: str,
    storage_path: str | Path | None = None,
) -> ModelStorageValidationResult:
    normalized_model_size = normalize_asr_model_size(model_size)
    using_default_storage = storage_path is None
    if storage_path is not None:
        selected_path_raw = Path(storage_path).expanduser()
        if _has_link_like_segment(selected_path_raw):
            raise SpeechModelStorageValidationError(
                f"The selected model storage folder uses a symbolic link or junction that LinguaSub will not manage automatically: {selected_path_raw}"
            )

        selected_path = selected_path_raw.resolve()
        if selected_path.exists() and not selected_path.is_dir():
            raise SpeechModelStorageValidationError(
                f"The selected model storage path is not a folder: {selected_path}"
            )

    target_dir, using_default_storage = _resolve_storage_root_from_selection(storage_path)
    existed_before = target_dir.exists()

    if target_dir.exists() and not target_dir.is_dir():
        raise SpeechModelStorageValidationError(
            f"The selected model storage path is not a folder: {target_dir}"
        )

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SpeechModelStorageValidationError(
            f"Could not create the selected model storage folder: {target_dir}"
        ) from exc

    if _has_link_like_segment(target_dir, stop_at=target_dir.parent.parent):
        raise SpeechModelStorageValidationError(
            f"The selected model storage folder uses a symbolic link or junction that LinguaSub will not manage automatically: {target_dir}"
        )

    write_test_file = target_dir / f".linguasub-write-check-{uuid.uuid4().hex}.tmp"
    try:
        with write_test_file.open("w", encoding="utf-8") as file:
            file.write("LinguaSub write check")
    except OSError as exc:
        raise SpeechModelStorageValidationError(
            f"The selected model storage folder is not writable: {target_dir}"
        ) from exc
    finally:
        if write_test_file.exists():
            write_test_file.unlink(missing_ok=True)

    ensure_model_root_metadata(
        target_dir,
        using_default_storage=using_default_storage,
    )

    free_space_bytes: int | None = None
    recommended_free_space_bytes = MIN_FREE_SPACE_BYTES[normalized_model_size]
    try:
        free_space_bytes = shutil.disk_usage(target_dir).free
    except OSError:
        free_space_bytes = None

    if (
        free_space_bytes is not None
        and free_space_bytes < recommended_free_space_bytes
    ):
        raise SpeechModelStorageValidationError(
            "The selected model storage folder does not have enough free space for "
            f"the '{normalized_model_size}' model. Available: {_format_bytes(free_space_bytes)}. "
            f"Recommended: {_format_bytes(recommended_free_space_bytes)}."
        )

    return ModelStorageValidationResult(
        path=str(target_dir),
        usingDefaultStorage=using_default_storage,
        createdDirectory=not existed_before,
        writable=True,
        freeSpaceBytes=free_space_bytes,
        recommendedFreeSpaceBytes=recommended_free_space_bytes,
    )


def resolve_installed_model_path(model_size: str) -> Path | None:
    normalized_model_size = normalize_asr_model_size(model_size)
    root = get_model_storage_dir()
    registry = _load_model_registry(root)

    configured_path = registry.get(normalized_model_size)
    if configured_path:
        resolved = Path(configured_path).expanduser().resolve()
        if _looks_like_model_directory(resolved):
            return resolved

    default_folder = root / normalized_model_size
    if _looks_like_model_directory(default_folder):
        return default_folder.resolve()

    # Also look through LinguaSub-managed model roots recorded in config so
    # models downloaded to a one-off custom folder still remain usable.
    for candidate_root in _collect_candidate_owned_roots_for_runtime(
        _load_config_managed_model_roots(),
        _load_config_managed_model_paths(),
    ):
        if candidate_root == root:
            continue

        candidate_registry = _load_model_registry(candidate_root)
        candidate_path = candidate_registry.get(normalized_model_size)
        if not candidate_path:
            continue

        resolved = Path(candidate_path).expanduser().resolve()
        if _looks_like_model_directory(resolved):
            return resolved

    return None


def resolve_ffmpeg_binary() -> Path | None:
    configured_binary = os.getenv(FFMPEG_PATH_ENV)
    if configured_binary:
        configured_path = Path(configured_binary).expanduser().resolve()
        if configured_path.exists() and configured_path.is_file():
            return configured_path

    for runtime_root in _iter_runtime_root_candidates():
        bundled_binary = runtime_root / "ffmpeg" / "ffmpeg.exe"
        if bundled_binary.exists() and bundled_binary.is_file():
            return bundled_binary.resolve()

    runtime_root = get_runtime_root()
    if runtime_root is not None:
        direct_binary = runtime_root / "ffmpeg.exe"
        if direct_binary.exists() and direct_binary.is_file():
            return direct_binary.resolve()

    ffmpeg_on_path = shutil.which("ffmpeg")
    if ffmpeg_on_path:
        return Path(ffmpeg_on_path).expanduser().resolve()

    return None


def resolve_ffprobe_binary() -> Path | None:
    for runtime_root in _iter_runtime_root_candidates():
        bundled_binary = runtime_root / "ffmpeg" / "ffprobe.exe"
        if bundled_binary.exists() and bundled_binary.is_file():
            return bundled_binary.resolve()

    runtime_root = get_runtime_root()
    if runtime_root is not None:
        direct_binary = runtime_root / "ffprobe.exe"
        if direct_binary.exists() and direct_binary.is_file():
            return direct_binary.resolve()

    configured_binary = os.getenv(FFPROBE_PATH_ENV)
    if configured_binary:
        configured_path = Path(configured_binary).expanduser().resolve()
        if configured_path.exists() and configured_path.is_file():
            return configured_path

    ffmpeg_binary = resolve_ffmpeg_binary()
    if ffmpeg_binary is not None:
        sibling_binary = ffmpeg_binary.with_name("ffprobe.exe")
        if sibling_binary.exists() and sibling_binary.is_file():
            return sibling_binary.resolve()

    ffprobe_on_path = shutil.which("ffprobe")
    if ffprobe_on_path:
        return Path(ffprobe_on_path).expanduser().resolve()

    return None


def get_faster_whisper_runtime_status() -> FasterWhisperRuntimeStatus:
    try:
        module = importlib.import_module("faster_whisper")
        importlib.import_module("faster_whisper.utils")
        importlib.import_module("ctranslate2")
        importlib.import_module("tokenizers")
    except Exception as exc:  # pragma: no cover - depends on local machine
        message = str(exc).strip() or exc.__class__.__name__
        return FasterWhisperRuntimeStatus(
            available=False,
            detectedPath=None,
            details=(
                "The packaged faster-whisper runtime could not be loaded. "
                f"{message}"
            ),
        )

    detected_path = getattr(module, "__file__", None)
    return FasterWhisperRuntimeStatus(
        available=True,
        detectedPath=str(Path(detected_path).resolve()) if detected_path else None,
        details=(
            "The local speech recognition runtime is available. Model files are "
            "managed separately in the user data directory."
        ),
    )


def _load_download_model_callable() -> Any:
    runtime_status = get_faster_whisper_runtime_status()
    if not runtime_status.available:
        raise FasterWhisperRuntimeUnavailableError(
            "The faster-whisper runtime is not available in this build. Reinstall "
            "LinguaSub or rebuild the backend sidecar with faster-whisper included."
        )

    try:
        utils_module = importlib.import_module("faster_whisper.utils")
        return getattr(utils_module, "download_model")
    except Exception as exc:  # pragma: no cover - depends on local machine
        message = str(exc).strip() or exc.__class__.__name__
        raise FasterWhisperRuntimeUnavailableError(
            "The faster-whisper runtime is installed, but LinguaSub could not load "
            f"its model downloader. {message}"
        ) from exc


def get_model_download_dir(
    storage_root: str | Path,
    model_size: str,
) -> Path:
    normalized_model_size = normalize_asr_model_size(model_size)
    return (Path(storage_root).expanduser().resolve() / normalized_model_size).resolve()


def _build_download_kwargs(
    download_model_callable: Any,
    storage_dir: Path,
    model_dir: Path,
) -> dict[str, Any]:
    parameters = inspect.signature(download_model_callable).parameters
    kwargs: dict[str, Any] = {}

    if "output_dir" in parameters:
        kwargs["output_dir"] = str(model_dir)
    elif "download_root" in parameters:
        kwargs["download_root"] = str(model_dir)

    if "cache_dir" in parameters:
        kwargs["cache_dir"] = str(storage_dir)

    if "local_files_only" in parameters:
        kwargs["local_files_only"] = False

    return kwargs


def _find_latest_model_directory(storage_dir: Path) -> Path | None:
    if not storage_dir.exists() or not storage_dir.is_dir():
        return None

    candidates: list[Path] = []
    for marker_name in ("config.json", "model.bin", "tokenizer.json"):
        for marker in storage_dir.rglob(marker_name):
            parent = marker.parent
            if _looks_like_model_directory(parent):
                candidates.append(parent)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda path: path.stat().st_mtime,
    ).resolve()


def _finalize_downloaded_model_path(
    source_path: Path,
    final_model_dir: Path,
    storage_dir: Path,
) -> Path:
    resolved_source = source_path.expanduser().resolve()
    resolved_target = final_model_dir.expanduser().resolve()
    resolved_storage_dir = storage_dir.expanduser().resolve()

    if resolved_source == resolved_target:
        return resolved_target

    _log_model_download(
        f"Finalizing model files from '{resolved_source}' to '{resolved_target}'."
    )

    try:
        resolved_target.relative_to(resolved_storage_dir)
    except ValueError as exc:
        raise SpeechModelDownloadFailedError(
            "Final move step failed. "
            f"Resolved model target '{resolved_target}' is outside the managed model root '{resolved_storage_dir}'."
        ) from exc

    if resolved_target.exists():
        try:
            if resolved_target.is_dir():
                shutil.rmtree(resolved_target)
            else:
                resolved_target.unlink(missing_ok=True)
        except OSError as exc:
            raise SpeechModelDownloadFailedError(
                "Final move step failed. "
                f"Could not clear the existing model folder at '{resolved_target}'."
            ) from exc

    try:
        shutil.copytree(resolved_source, resolved_target)
    except OSError as exc:
        raise SpeechModelDownloadFailedError(
            "Final move step failed. "
            f"Could not copy model files from '{resolved_source}' to '{resolved_target}'."
        ) from exc

    return resolved_target


def _resolve_downloaded_model_path(
    result: Any,
    storage_dir: Path,
    model_dir: Path,
    model_size: AsrModelSize,
) -> Path:
    if isinstance(result, (str, os.PathLike)):
        resolved = Path(result).expanduser().resolve()
        _log_model_download(f"Downloader returned path: {resolved}")
        if _looks_like_model_directory(resolved):
            return resolved

        nested_result_dir = resolved / model_size
        if _looks_like_model_directory(nested_result_dir):
            return nested_result_dir.resolve()

        nested_result_candidate = _find_latest_model_directory(resolved)
        if nested_result_candidate is not None:
            return nested_result_candidate

    if _looks_like_model_directory(model_dir):
        return model_dir.resolve()

    default_folder = storage_dir / model_size
    if _looks_like_model_directory(default_folder):
        return default_folder.resolve()

    for search_root in (model_dir, storage_dir):
        latest_candidate = _find_latest_model_directory(search_root)
        if latest_candidate is not None:
            return latest_candidate

    result_text = str(result).strip() if result is not None else "<none>"
    raise SpeechModelDownloadFailedError(
        "Location resolution step failed. "
        f"LinguaSub could not locate verified model files for '{model_size}'. "
        f"Downloader output was: {result_text}. "
        f"Expected target: {model_dir}."
    )


def download_speech_model(
    model_size: str,
    storage_path: str | Path | None = None,
) -> tuple[Path, ModelStorageValidationResult]:
    normalized_model_size = normalize_asr_model_size(model_size)
    validation = validate_model_storage_directory(
        model_size=normalized_model_size,
        storage_path=storage_path,
    )
    storage_dir = ensure_model_storage_dir(validation.path)
    model_dir = get_model_download_dir(storage_dir, normalized_model_size)
    model_dir.mkdir(parents=True, exist_ok=True)
    download_model_callable = _load_download_model_callable()
    download_kwargs = _build_download_kwargs(
        download_model_callable,
        storage_dir,
        model_dir,
    )
    _log_model_download(
        f"Preparing '{normalized_model_size}' download. "
        f"Managed root='{storage_dir}', final target='{model_dir}'."
    )
    _log_model_download(
        f"Downloader request for '{normalized_model_size}': "
        f"output_dir='{download_kwargs.get('output_dir') or download_kwargs.get('download_root') or '<default>'}', "
        f"cache_dir='{download_kwargs.get('cache_dir') or '<default>'}'."
    )

    try:
        result = download_model_callable(
            normalized_model_size,
            **download_kwargs,
        )
    except Exception as exc:  # pragma: no cover - depends on local runtime
        message = str(exc).strip() or exc.__class__.__name__
        raise SpeechModelDownloadFailedError(
            f"Download step failed for the '{normalized_model_size}' speech model. {message}"
        ) from exc

    resolved_model_source = _resolve_downloaded_model_path(
        result=result,
        storage_dir=storage_dir,
        model_dir=model_dir,
        model_size=normalized_model_size,
    )
    _log_model_download(
        f"Resolved downloaded model source for '{normalized_model_size}' to '{resolved_model_source}'."
    )
    resolved_model_path = _finalize_downloaded_model_path(
        resolved_model_source,
        model_dir,
        storage_dir,
    )
    is_valid, missing_files = verify_model_directory(resolved_model_path)
    _log_model_download(
        f"Verification result for '{normalized_model_size}' at '{resolved_model_path}': "
        f"{'ok' if is_valid else 'missing ' + ', '.join(missing_files)}"
    )
    if not is_valid:
        missing_text = ", ".join(missing_files)
        raise SpeechModelDownloadFailedError(
            "Verification step failed. "
            f"The '{normalized_model_size}' model download is incomplete at '{resolved_model_path}'. "
            f"Missing: {missing_text}. Please retry."
        )

    try:
        register_model_path(normalized_model_size, resolved_model_path)
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        raise SpeechModelDownloadFailedError(
            "Registry update step failed. "
            f"LinguaSub verified the '{normalized_model_size}' model at '{resolved_model_path}', "
            f"but could not write the model registry. {message}"
        ) from exc

    _log_model_download(
        f"Registered '{normalized_model_size}' model at '{resolved_model_path}' successfully."
    )
    return resolved_model_path, validation


def get_download_status() -> SpeechModelDownloadStatus:
    with _download_lock:
        return SpeechModelDownloadStatus(
            active=_download_status.active,
            modelSize=_download_status.modelSize,
            status=_download_status.status,
            targetPath=_download_status.targetPath,
            usingDefaultStorage=_download_status.usingDefaultStorage,
            progress=_download_status.progress,
            message=_download_status.message,
            error=_download_status.error,
        )


def _set_download_status(
    *,
    active: bool,
    model_size: AsrModelSize | None,
    status: SpeechModelDownloadState,
    target_path: str | None,
    using_default_storage: bool,
    progress: int,
    message: str,
    error: str | None = None,
) -> None:
    with _download_lock:
        _download_status.active = active
        _download_status.modelSize = model_size
        _download_status.status = status
        _download_status.targetPath = target_path
        _download_status.usingDefaultStorage = using_default_storage
        _download_status.progress = progress
        _download_status.message = message
        _download_status.error = error


def _download_model_worker(
    model_size: AsrModelSize,
    storage_path: str | None,
    remember_storage_path: bool,
) -> None:
    target_model_path: str | None = None
    using_default_storage = storage_path is None
    try:
        validation = validate_model_storage_directory(model_size, storage_path)
        target_model_dir = get_model_download_dir(validation.path, model_size)
        target_model_path = str(target_model_dir)
        _set_download_status(
            active=True,
            model_size=model_size,
            status="starting",
            target_path=target_model_path,
            using_default_storage=validation.usingDefaultStorage,
            progress=10,
            message=f"Preparing the '{model_size}' speech model download.",
        )
        _load_download_model_callable()

        _set_download_status(
            active=True,
            model_size=model_size,
            status="downloading",
            target_path=target_model_path,
            using_default_storage=validation.usingDefaultStorage,
            progress=45,
            message=f"Downloading the '{model_size}' speech model to {target_model_dir}.",
        )
        resolved_model_path, _ = download_speech_model(model_size, validation.path)

        _set_download_status(
            active=True,
            model_size=model_size,
            status="downloading",
            target_path=str(resolved_model_path),
            using_default_storage=validation.usingDefaultStorage,
            progress=85,
            message=f"Verifying model files at {resolved_model_path}.",
        )
        is_valid, missing_files = verify_model_directory(resolved_model_path)
        if not is_valid:
            missing_text = ", ".join(missing_files)
            raise SpeechModelDownloadFailedError(
                f"The model download is incomplete. Missing: {missing_text}. Please retry."
            )

        if remember_storage_path:
            if validation.usingDefaultStorage:
                persist_model_storage_preference(None)
            else:
                persist_model_storage_preference(validation.path)

        _set_download_status(
            active=False,
            model_size=model_size,
            status="done",
            target_path=str(resolved_model_path),
            using_default_storage=validation.usingDefaultStorage,
            progress=100,
            message=f"The '{model_size}' speech model is ready to use.",
            error=None,
        )
    except SpeechRuntimeError as exc:
        _set_download_status(
            active=False,
            model_size=model_size,
            status="error",
            target_path=target_model_path,
            using_default_storage=using_default_storage,
            progress=0,
            message=f"Model download failed for '{model_size}'.",
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        message = str(exc).strip() or exc.__class__.__name__
        _set_download_status(
            active=False,
            model_size=model_size,
            status="error",
            target_path=target_model_path,
            using_default_storage=using_default_storage,
            progress=0,
            message=f"Model download failed for '{model_size}'.",
            error=message,
        )


def start_model_download(
    model_size: str,
    storage_path: str | None = None,
    remember_storage_path: bool = True,
) -> SpeechModelDownloadStatus:
    normalized_model_size = normalize_asr_model_size(model_size)
    resolved_target_root = _resolve_storage_root_from_selection(storage_path)[0]
    resolved_target_path = get_model_download_dir(
        resolved_target_root,
        normalized_model_size,
    )
    existing_model_path = resolve_installed_model_path(normalized_model_size)
    if existing_model_path is not None:
        _set_download_status(
            active=False,
            model_size=normalized_model_size,
            status="done",
            target_path=str(existing_model_path),
            using_default_storage=storage_path is None,
            progress=100,
            message=f"The '{normalized_model_size}' speech model is already available.",
        )
        return get_download_status()

    current_status = get_download_status()
    if current_status.active:
        if current_status.modelSize == normalized_model_size:
            return current_status
        raise SpeechModelDownloadConflictError(
            f"LinguaSub is already downloading the '{current_status.modelSize}' speech model."
        )

    _set_download_status(
        active=True,
        model_size=normalized_model_size,
        status="starting",
        target_path=str(resolved_target_path),
        using_default_storage=storage_path is None,
        progress=5,
        message=f"Queued the '{normalized_model_size}' speech model download.",
    )

    worker = threading.Thread(
        target=_download_model_worker,
        args=(normalized_model_size, storage_path, remember_storage_path),
        daemon=True,
        name=f"linguasub-model-download-{normalized_model_size}",
    )
    worker.start()
    return get_download_status()


def _load_config_managed_model_paths() -> set[str]:
    try:
        config = load_config()
    except Exception:
        return set()

    return {
        str(Path(item).expanduser().resolve())
        for item in config.managedModelPaths
        if str(item).strip()
    }


def _load_config_managed_model_roots() -> set[str]:
    try:
        config = load_config()
    except Exception:
        return set()

    roots = {
        str(Path(item).expanduser().resolve())
        for item in config.managedModelRoots
        if str(item).strip()
    }

    saved_root = config.modelStoragePath.strip()
    if saved_root:
        resolved_saved_root = Path(saved_root).expanduser().resolve()
        if _is_owned_model_root(resolved_saved_root):
            roots.add(str(resolved_saved_root))

    for item in config.managedModelPaths:
        if not str(item).strip():
            continue

        model_path = Path(item).expanduser().resolve()
        parents_to_check = [model_path.parent, *list(model_path.parents[:4])]
        for parent in parents_to_check:
            if _is_owned_model_root(parent):
                roots.add(str(parent.resolve()))
                break

    return roots


def _collect_candidate_owned_roots_for_runtime(
    config_model_roots: set[str],
    config_model_paths: set[str],
) -> list[Path]:
    candidates: list[Path] = []
    default_root = get_default_model_storage_dir().resolve()
    candidates.append(default_root)

    saved_root = get_saved_model_storage_path()
    if saved_root is not None:
        candidates.append(saved_root.resolve())

    for item in config_model_roots:
        candidates.append(Path(item).expanduser().resolve())

    for item in config_model_paths:
        model_path = Path(item).expanduser().resolve()
        parents_to_check = [model_path.parent, *list(model_path.parents[:4])]
        for parent in parents_to_check:
            if _is_owned_model_root(parent):
                candidates.append(parent.resolve())
                break

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    return deduped


def _path_is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def cleanup_downloaded_models() -> SpeechModelCleanupResult:
    if get_download_status().active:
        raise SpeechModelCleanupError(
            "LinguaSub is still downloading a speech model. Wait for it to finish before uninstall cleanup."
        )

    config_model_paths = _load_config_managed_model_paths()
    config_model_roots = _load_config_managed_model_roots()
    candidate_roots = [
        Path(item).expanduser().resolve()
        for item in config_model_roots
    ]
    result = SpeechModelCleanupResult()

    removed_model_paths: list[Path] = []
    removed_root_paths: list[Path] = []

    for item in config_model_paths:
        model_path = Path(item).expanduser().resolve()
        parent_chain = [model_path.parent, *list(model_path.parents[:4])]
        if not any(str(parent.resolve()) in config_model_roots for parent in parent_chain):
            result.protectedPaths.append(str(model_path.parent))

    for root in candidate_roots:
        if not root.exists():
            continue

        if _has_link_like_segment(root, stop_at=root):
            result.protectedPaths.append(str(root))
            continue

        if not _is_owned_model_root(root):
            result.protectedPaths.append(str(root))
            continue

        manifest = _load_model_registry(root)
        removable_entries: dict[str, Path] = {}
        remaining_entries: dict[str, str] = {}

        for model_size, model_path_value in manifest.items():
            model_path = Path(model_path_value).expanduser().resolve()
            model_path_string = str(model_path)

            if not _path_is_within_root(model_path, root):
                result.protectedPaths.append(model_path_string)
                remaining_entries[model_size] = model_path_string
                continue

            if _has_link_like_segment(model_path, stop_at=root):
                result.protectedPaths.append(model_path_string)
                remaining_entries[model_size] = model_path_string
                continue

            if model_path_string not in config_model_paths:
                result.protectedPaths.append(model_path_string)
                remaining_entries[model_size] = model_path_string
                continue

            removable_entries[model_size] = model_path

        for model_size, model_path in removable_entries.items():
            if model_path.exists():
                if model_path.is_dir():
                    shutil.rmtree(model_path)
                else:
                    model_path.unlink(missing_ok=True)
                result.removedModelPaths.append(str(model_path))
            else:
                result.skippedPaths.append(str(model_path))

            removed_model_paths.append(model_path)

        if remaining_entries:
            _save_model_registry(remaining_entries, root)
        elif removable_entries:
            registry_path = get_model_registry_path(root)
            marker_path = get_model_root_marker_path(root)
            for metadata_path in (registry_path, marker_path):
                if metadata_path.exists():
                    metadata_path.unlink(missing_ok=True)
                    result.removedMetadataPaths.append(str(metadata_path))

            if root.exists() and not any(root.iterdir()):
                root.rmdir()
                result.removedRootPaths.append(str(root))
                removed_root_paths.append(root)

    if removed_model_paths or removed_root_paths:
        _remove_managed_references(removed_model_paths, removed_root_paths)

    cleanup_config = load_config()
    saved_storage_path = cleanup_config.modelStoragePath.strip()
    if (
        saved_storage_path
        and str(Path(saved_storage_path).expanduser().resolve())
        in {str(path.expanduser().resolve()) for path in removed_root_paths}
    ):
        cleanup_config.modelStoragePath = ""
        save_config(cleanup_config)

    if result.removedModelPaths:
        result.message = (
            f"Removed {len(result.removedModelPaths)} LinguaSub-managed model "
            f"{'directory' if len(result.removedModelPaths) == 1 else 'directories'} safely before uninstall."
        )
    else:
        result.message = (
            "No LinguaSub-managed downloaded models were removed. "
            "Only marked and recorded model directories qualify for cleanup."
        )

    return result


def build_speech_model_statuses() -> list[SpeechModelStatus]:
    runtime_status = get_faster_whisper_runtime_status()
    current_download = get_download_status()
    statuses: list[SpeechModelStatus] = []

    for model_size in SUPPORTED_ASR_MODEL_SIZES:
        label = model_size.capitalize()
        detected_path = resolve_installed_model_path(model_size)

        if current_download.active and current_download.modelSize == model_size:
            statuses.append(
                SpeechModelStatus(
                    size=model_size,
                    label=label,
                    available=False,
                    status="downloading",
                    detectedPath=current_download.targetPath or (str(detected_path) if detected_path else None),
                    statusText=current_download.message,
                    details="LinguaSub is downloading this model in the background.",
                    actionHint="Wait for the current download to finish.",
                )
            )
            continue

        if (
            current_download.status == "error"
            and current_download.modelSize == model_size
            and detected_path is None
        ):
            statuses.append(
                SpeechModelStatus(
                    size=model_size,
                    label=label,
                    available=False,
                    status="error",
                    detectedPath=current_download.targetPath,
                    statusText=current_download.message or "Model download failed.",
                    details=current_download.error or "LinguaSub could not verify the downloaded model files.",
                    actionHint="Check the target folder and retry the model download.",
                )
            )
            continue

        if not runtime_status.available:
            statuses.append(
                SpeechModelStatus(
                    size=model_size,
                    label=label,
                    available=False,
                    status="unavailable",
                    detectedPath=None,
                    statusText="The faster-whisper runtime is missing.",
                    details=(
                        "Model files are managed separately, but LinguaSub cannot use "
                        "or download them until the faster-whisper runtime is bundled."
                    ),
                    actionHint="Rebuild or reinstall LinguaSub with the faster-whisper runtime included.",
                )
            )
            continue

        if detected_path is not None:
            statuses.append(
                SpeechModelStatus(
                    size=model_size,
                    label=label,
                    available=True,
                    status="ready",
                    detectedPath=str(detected_path),
                    statusText="Installed and verified.",
                    details=(
                        "This model is available for local media transcription."
                    ),
                    actionHint="You can start recognition with this model immediately.",
                )
            )
            continue

        statuses.append(
            SpeechModelStatus(
                size=model_size,
                label=label,
                available=False,
                status="missing",
                detectedPath=None,
                statusText="Not downloaded yet.",
                details=(
                    "LinguaSub keeps Whisper model files out of the installer and "
                    "downloads them on first use."
                ),
                actionHint="Use the Download Model action below to install this model.",
            )
        )

    return statuses


def has_any_ready_speech_model() -> bool:
    return any(model.available for model in build_speech_model_statuses())
