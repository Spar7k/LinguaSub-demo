"""Persistent recent-task and diagnostic log storage for LinguaSub."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from time import strftime
from typing import Any, Literal

from .config_service import get_config_path
from .models import JsonModel

TaskMode = Literal["extractAndTranslate", "translateSubtitle"]
TaskEngineType = Literal[
    "cloudTranscription",
    "localTranscription",
    "subtitleImport",
]
TaskStatus = Literal[
    "queued",
    "transcribing",
    "translating",
    "editing",
    "exporting",
    "done",
    "error",
    "cancelled",
]
TaskLogLevel = Literal["info", "warning", "error"]

MAX_HISTORY_ITEMS = 30


class TaskHistoryError(RuntimeError):
    """Base error for recent-task persistence."""


@dataclass(slots=True)
class SubtitleSummary(JsonModel):
    segmentCount: int = 0
    translatedCount: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SubtitleSummary | None":
        if not isinstance(data, dict):
            return None

        return cls(
            segmentCount=int(data.get("segmentCount", 0) or 0),
            translatedCount=int(data.get("translatedCount", 0) or 0),
        )


@dataclass(slots=True)
class TaskLogEntry(JsonModel):
    logId: str
    timestamp: str
    level: TaskLogLevel
    message: str
    details: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskLogEntry":
        level = str(data.get("level", "info")).strip().lower()
        if level not in {"info", "warning", "error"}:
            level = "info"

        details = data.get("details")
        return cls(
            logId=str(data.get("logId", "")).strip() or f"log-{strftime('%Y%m%d-%H%M%S')}",
            timestamp=str(data.get("timestamp", "")).strip() or "",
            level=level,  # type: ignore[arg-type]
            message=str(data.get("message", "")).strip() or "Task event",
            details=str(details).strip() if isinstance(details, str) and details.strip() else None,
        )


@dataclass(slots=True)
class TaskHistoryRecord(JsonModel):
    taskId: str
    sourceFilePath: str
    sourceFileName: str
    taskMode: TaskMode
    sourceLanguage: str
    targetLanguage: str
    outputFormats: list[str] = field(default_factory=list)
    engineType: TaskEngineType = "subtitleImport"
    status: TaskStatus = "queued"
    createdAt: str = ""
    updatedAt: str = ""
    exportPaths: list[str] = field(default_factory=list)
    errorMessage: str | None = None
    subtitleSummary: SubtitleSummary | None = None
    importSnapshot: dict[str, Any] | None = None
    projectSnapshot: dict[str, Any] | None = None
    logs: list[TaskLogEntry] = field(default_factory=list)
    transcriptionProvider: str | None = None
    transcriptionModelSize: str | None = None
    transcriptionQualityPreset: str | None = None
    translationProvider: str | None = None
    translationModel: str | None = None
    outputMode: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskHistoryRecord":
        task_mode = str(data.get("taskMode", "extractAndTranslate")).strip()
        if task_mode not in {"extractAndTranslate", "translateSubtitle"}:
            task_mode = "extractAndTranslate"

        engine_type = str(data.get("engineType", "subtitleImport")).strip()
        if engine_type not in {
            "cloudTranscription",
            "localTranscription",
            "subtitleImport",
        }:
            engine_type = "subtitleImport"

        status = str(data.get("status", "queued")).strip()
        if status not in {
            "queued",
            "transcribing",
            "translating",
            "editing",
            "exporting",
            "done",
            "error",
            "cancelled",
        }:
            status = "queued"

        return cls(
            taskId=str(data.get("taskId", "")).strip(),
            sourceFilePath=str(data.get("sourceFilePath", "")).strip(),
            sourceFileName=str(data.get("sourceFileName", "")).strip(),
            taskMode=task_mode,  # type: ignore[arg-type]
            sourceLanguage=str(data.get("sourceLanguage", "auto")).strip() or "auto",
            targetLanguage=str(data.get("targetLanguage", "zh-CN")).strip() or "zh-CN",
            outputFormats=[
                str(item).strip()
                for item in data.get("outputFormats", [])
                if str(item).strip()
            ],
            engineType=engine_type,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            createdAt=str(data.get("createdAt", "")).strip(),
            updatedAt=str(data.get("updatedAt", "")).strip(),
            exportPaths=[
                str(item).strip()
                for item in data.get("exportPaths", [])
                if str(item).strip()
            ],
            errorMessage=(
                str(data.get("errorMessage")).strip()
                if isinstance(data.get("errorMessage"), str)
                and str(data.get("errorMessage")).strip()
                else None
            ),
            subtitleSummary=SubtitleSummary.from_dict(data.get("subtitleSummary")),
            importSnapshot=data.get("importSnapshot")
            if isinstance(data.get("importSnapshot"), dict)
            else None,
            projectSnapshot=data.get("projectSnapshot")
            if isinstance(data.get("projectSnapshot"), dict)
            else None,
            logs=[
                TaskLogEntry.from_dict(item)
                for item in data.get("logs", [])
                if isinstance(item, dict)
            ],
            transcriptionProvider=(
                str(data.get("transcriptionProvider")).strip()
                if isinstance(data.get("transcriptionProvider"), str)
                and str(data.get("transcriptionProvider")).strip()
                else None
            ),
            transcriptionModelSize=(
                str(data.get("transcriptionModelSize")).strip()
                if isinstance(data.get("transcriptionModelSize"), str)
                and str(data.get("transcriptionModelSize")).strip()
                else None
            ),
            transcriptionQualityPreset=(
                str(data.get("transcriptionQualityPreset")).strip()
                if isinstance(data.get("transcriptionQualityPreset"), str)
                and str(data.get("transcriptionQualityPreset")).strip()
                else None
            ),
            translationProvider=(
                str(data.get("translationProvider")).strip()
                if isinstance(data.get("translationProvider"), str)
                and str(data.get("translationProvider")).strip()
                else None
            ),
            translationModel=(
                str(data.get("translationModel")).strip()
                if isinstance(data.get("translationModel"), str)
                and str(data.get("translationModel")).strip()
                else None
            ),
            outputMode=(
                str(data.get("outputMode")).strip()
                if isinstance(data.get("outputMode"), str)
                and str(data.get("outputMode")).strip()
                else None
            ),
        )


def _build_invalid_history_backup_path(history_path: Path) -> Path:
    timestamp = strftime("%Y%m%d-%H%M%S")
    return history_path.with_name(
        f"{history_path.stem}.invalid-{timestamp}{history_path.suffix}"
    )


def get_task_history_path() -> Path:
    config_path = get_config_path()
    return config_path.with_name("task-history.json")


def ensure_task_history_parent_exists() -> Path:
    history_path = get_task_history_path()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    return history_path


def _reset_invalid_history(history_path: Path) -> list[TaskHistoryRecord]:
    if history_path.exists():
        backup_path = _build_invalid_history_backup_path(history_path)
        try:
            history_path.replace(backup_path)
        except OSError:
            try:
                backup_path.write_text(
                    history_path.read_text(encoding="utf-8", errors="replace"),
                    encoding="utf-8",
                )
                history_path.unlink(missing_ok=True)
            except OSError:
                pass

    save_task_history([])
    return []


def _sort_history(records: list[TaskHistoryRecord]) -> list[TaskHistoryRecord]:
    return sorted(records, key=lambda item: item.updatedAt or item.createdAt, reverse=True)


def load_task_history() -> list[TaskHistoryRecord]:
    history_path = ensure_task_history_parent_exists()
    if not history_path.exists():
        save_task_history([])
        return []

    try:
        with history_path.open("r", encoding="utf-8") as file:
            raw_data = json.load(file)
        if not isinstance(raw_data, list):
            raise ValueError("Task history JSON must be a list.")

        records = [
            TaskHistoryRecord.from_dict(item)
            for item in raw_data
            if isinstance(item, dict)
            and str(item.get("taskId", "")).strip()
            and str(item.get("sourceFilePath", "")).strip()
        ]
        return _sort_history(records)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return _reset_invalid_history(history_path)


def save_task_history(records: list[TaskHistoryRecord | dict[str, Any]]) -> list[TaskHistoryRecord]:
    normalized_records = [
        item if isinstance(item, TaskHistoryRecord) else TaskHistoryRecord.from_dict(item)
        for item in records
    ]
    history_path = ensure_task_history_parent_exists()

    trimmed_records = _sort_history(normalized_records)[:MAX_HISTORY_ITEMS]
    with history_path.open("w", encoding="utf-8") as file:
        json.dump(
            [item.to_dict() for item in trimmed_records],
            file,
            ensure_ascii=False,
            indent=2,
        )

    return trimmed_records


def upsert_task_history_record(record: TaskHistoryRecord | dict[str, Any]) -> TaskHistoryRecord:
    normalized_record = (
        record if isinstance(record, TaskHistoryRecord) else TaskHistoryRecord.from_dict(record)
    )
    if not normalized_record.taskId or not normalized_record.sourceFilePath:
        raise TaskHistoryError("Task history records must include taskId and sourceFilePath.")

    history = load_task_history()
    next_history: list[TaskHistoryRecord] = [normalized_record]
    next_history.extend(item for item in history if item.taskId != normalized_record.taskId)
    save_task_history(next_history)
    return normalized_record


loadTaskHistory = load_task_history
saveTaskHistory = save_task_history
upsertTaskHistoryRecord = upsert_task_history_record
