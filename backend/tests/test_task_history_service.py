"""Tests for recent-task persistence and recovery."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.task_history_service import load_task_history, upsert_task_history_record


class TaskHistoryServiceTests(unittest.TestCase):
    def test_task_history_recovers_from_invalid_json(self) -> None:
        sandbox = Path(__file__).resolve().parent / "fixtures" / "runtime-sandbox" / "task-history-recovery"
        if sandbox.exists():
            shutil.rmtree(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
        config_path = sandbox / "app-config.json"
        history_path = sandbox / "task-history.json"
        config_path.write_text("{}", encoding="utf-8")
        history_path.write_text("{ invalid json", encoding="utf-8")

        with patch.dict(
            "os.environ",
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            history = load_task_history()

        self.assertEqual(history, [])
        self.assertTrue(history_path.exists())
        recovered_payload = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual(recovered_payload, [])
        self.assertTrue(list(sandbox.glob("task-history.invalid-*.json")))

    def test_upsert_task_history_keeps_latest_task_first(self) -> None:
        sandbox = Path(__file__).resolve().parent / "fixtures" / "runtime-sandbox" / "task-history-upsert"
        if sandbox.exists():
            shutil.rmtree(sandbox)
        sandbox.mkdir(parents=True, exist_ok=True)
        config_path = sandbox / "app-config.json"
        config_path.write_text("{}", encoding="utf-8")

        first_task = {
            "taskId": "task-001",
            "sourceFilePath": "D:/media/demo-a.mp4",
            "sourceFileName": "demo-a.mp4",
            "taskMode": "extractAndTranslate",
            "sourceLanguage": "auto",
            "targetLanguage": "zh-CN",
            "outputFormats": [],
            "engineType": "cloudTranscription",
            "status": "done",
            "createdAt": "2026-04-18T10:00:00Z",
            "updatedAt": "2026-04-18T10:00:00Z",
            "exportPaths": [],
            "logs": [],
        }
        second_task = {
            **first_task,
            "taskId": "task-002",
            "sourceFilePath": "D:/media/demo-b.srt",
            "sourceFileName": "demo-b.srt",
            "taskMode": "translateSubtitle",
            "engineType": "subtitleImport",
            "createdAt": "2026-04-18T11:00:00Z",
            "updatedAt": "2026-04-18T11:00:00Z",
        }

        with patch.dict(
            "os.environ",
            {"LINGUASUB_CONFIG_PATH": str(config_path)},
            clear=False,
        ):
            upsert_task_history_record(first_task)
            upsert_task_history_record(second_task)
            loaded = load_task_history()

        self.assertEqual([item.taskId for item in loaded], ["task-002", "task-001"])


if __name__ == "__main__":
    unittest.main()
