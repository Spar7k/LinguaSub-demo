"""Tests for the backend command-line entry points."""

from __future__ import annotations

import json
import unittest
from http import HTTPStatus
from io import StringIO
from unittest.mock import patch

import backend.run_server as run_server_module
from backend.app.export_service import ExportResult
from backend.app.server import LinguaSubRequestHandler
from backend.app.speech_runtime_service import SpeechModelCleanupResult


class RunServerCliTests(unittest.TestCase):
    def test_cleanup_models_command_uses_runtime_overrides(self) -> None:
        cleanup_result = SpeechModelCleanupResult(
            removedModelPaths=["D:/models/small"],
            removedRootPaths=["D:/models"],
            removedMetadataPaths=["D:/models/.linguasub-model-root.json"],
            skippedPaths=[],
            protectedPaths=[],
            message="ok",
        )

        stdout = StringIO()
        stderr = StringIO()

        with (
            patch("backend.run_server.cleanup_downloaded_models", return_value=cleanup_result),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
            patch.dict("os.environ", {}, clear=False),
        ):
            exit_code = run_server_module.main(
                [
                    "--cleanup-models",
                    "--config-path",
                    "D:/cfg/app-config.json",
                    "--model-dir",
                    "D:/cfg/speech-models",
                ]
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["removedModelPaths"], ["D:/models/small"])

    def test_default_mode_runs_http_server(self) -> None:
        with patch("backend.run_server.run_server") as mocked_run_server:
            exit_code = run_server_module.main([])

        self.assertEqual(exit_code, 0)
        mocked_run_server.assert_called_once_with()


class CommandAgentWordRouteTests(unittest.TestCase):
    def test_command_agent_word_route_dispatches_handler(self) -> None:
        handler = object.__new__(LinguaSubRequestHandler)
        handler.path = "/export/command-agent-word"
        called_paths: list[str] = []

        def fake_handler(instance: LinguaSubRequestHandler) -> None:
            called_paths.append(instance.path)

        with patch.object(
            LinguaSubRequestHandler,
            "_handle_command_agent_word_export",
            fake_handler,
        ):
            handler.do_POST()

        self.assertEqual(called_paths, ["/export/command-agent-word"])

    def test_command_agent_word_handler_calls_export_service(self) -> None:
        payload = {
            "instruction": "Create a classroom presentation script",
            "result": {
                "intent": "presentation_script",
                "title": "Classroom Presentation Script",
                "summary": "Overview",
                "content": "Body",
                "suggestedActions": ["Export Word"],
            },
            "contextSummary": {
                "videoName": "lesson.mp4",
                "subtitleCount": 86,
                "translatedCount": 86,
                "translationCoverage": 100,
                "sourceLanguage": "en",
                "targetLanguage": "zh",
                "bilingualMode": "bilingual",
            },
            "createdAt": "2026-05-03T12:00:00Z",
            "sourceFilePath": "D:/videos/lesson.srt",
            "fileName": "agent-result",
        }
        handler = object.__new__(LinguaSubRequestHandler)
        responses: list[tuple[HTTPStatus, dict[str, object]]] = []
        errors: list[tuple[HTTPStatus, dict[str, str]]] = []
        captured: dict[str, object] = {}

        handler._read_json_body = lambda: payload
        handler._send_json = lambda body, status=HTTPStatus.OK: responses.append(
            (status, body)
        )
        handler._send_error_json = lambda status, message: errors.append(
            (status, {"error": message})
        )

        def fake_export_command_agent_word(**kwargs: object) -> ExportResult:
            captured.update(kwargs)
            return ExportResult(
                path="D:/videos/agent-result.docx",
                directory="D:/videos",
                fileName="agent-result.docx",
                format="command_agent_word",
                bilingual=False,
                wordMode=None,
                count=1,
            )

        with patch(
            "backend.app.server.export_command_agent_word",
            side_effect=fake_export_command_agent_word,
        ):
            handler._handle_command_agent_word_export()

        self.assertEqual(errors, [])
        self.assertEqual(captured["instruction"], payload["instruction"])
        self.assertEqual(captured["result"], payload["result"])
        self.assertEqual(captured["context_summary"], payload["contextSummary"])
        self.assertEqual(captured["created_at"], payload["createdAt"])
        self.assertEqual(captured["source_file_path"], payload["sourceFilePath"])
        self.assertEqual(captured["file_name"], payload["fileName"])
        self.assertEqual(responses[0][0], HTTPStatus.OK)
        self.assertEqual(responses[0][1]["status"], "done")
        self.assertEqual(responses[0][1]["format"], "command_agent_word")

    def test_command_agent_word_handler_rejects_missing_result(self) -> None:
        handler = object.__new__(LinguaSubRequestHandler)
        responses: list[tuple[HTTPStatus, dict[str, object]]] = []
        errors: list[tuple[HTTPStatus, dict[str, str]]] = []

        handler._read_json_body = lambda: {"sourceFilePath": "D:/videos/lesson.srt"}
        handler._send_json = lambda body, status=HTTPStatus.OK: responses.append(
            (status, body)
        )
        handler._send_error_json = lambda status, message: errors.append(
            (status, {"error": message})
        )

        handler._handle_command_agent_word_export()

        self.assertEqual(responses, [])
        self.assertEqual(errors[0][0], HTTPStatus.BAD_REQUEST)
        self.assertEqual(errors[0][1], {"error": "Command Agent result is required."})


if __name__ == "__main__":
    unittest.main()
