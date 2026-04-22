"""Tests for the backend command-line entry points."""

from __future__ import annotations

import json
import unittest
from io import StringIO
from unittest.mock import patch

import backend.run_server as run_server_module
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


if __name__ == "__main__":
    unittest.main()
