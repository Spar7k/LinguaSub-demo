"""Tests for environment and first-run checks."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.environment_service import build_startup_check
from backend.app.models import create_default_app_config
from backend.app.speech_runtime_service import (
    FasterWhisperRuntimeStatus,
    SpeechModelDownloadStatus,
    SpeechModelStatus,
)


class EnvironmentServiceTests(unittest.TestCase):
    def test_build_startup_check_reports_missing_runtime_dependencies(self) -> None:
        config = create_default_app_config()
        config.apiKey = ""

        with (
            patch("backend.app.environment_service.load_config", return_value=config),
            patch("backend.app.environment_service.resolve_ffmpeg_binary", return_value=None),
            patch(
                "backend.app.environment_service.get_faster_whisper_runtime_status",
                return_value=FasterWhisperRuntimeStatus(
                    available=False,
                    detectedPath=None,
                    details="runtime missing",
                ),
            ),
            patch(
                "backend.app.environment_service.build_speech_model_statuses",
                return_value=[
                    SpeechModelStatus(
                        size="small",
                        label="Small",
                        available=False,
                        status="unavailable",
                        detectedPath=None,
                        statusText="runtime missing",
                        details="runtime missing",
                        actionHint="rebuild runtime",
                    )
                ],
            ),
            patch(
                "backend.app.environment_service.get_download_status",
                return_value=SpeechModelDownloadStatus(),
            ),
            patch(
                "backend.app.environment_service.get_config_path",
                return_value=Path("D:/codetest/LinguaSub/backend/storage/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_recommended_release_config_path",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_default_user_data_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub"),
            ),
            patch(
                "backend.app.environment_service.get_default_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
            patch(
                "backend.app.environment_service.get_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
        ):
            report = build_startup_check()

        self.assertEqual(report.mode, "development")
        self.assertTrue(report.backendReachable)
        self.assertTrue(report.readyForSrtWorkflow)
        self.assertFalse(report.readyForMediaWorkflow)
        self.assertFalse(report.readyForCloudTranscription)
        self.assertFalse(report.readyForLocalTranscription)
        self.assertFalse(report.apiKeyConfigured)
        self.assertEqual(
            Path(report.defaultSpeechModelStorageDir),
            Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
        )
        self.assertEqual(len(report.dependencies), 4)
        self.assertTrue(any(item.key == "backend" and item.available for item in report.dependencies))
        self.assertTrue(
            any(item.key == "cloudTranscriptionConfig" and not item.available for item in report.dependencies)
        )
        self.assertTrue(any("API key" in warning for warning in report.warnings))
        self.assertTrue(any("Cloud transcription" in warning for warning in report.warnings))
        self.assertFalse(any("FFmpeg" in warning for warning in report.warnings))
        self.assertFalse(any("faster-whisper runtime" in warning for warning in report.warnings))

    def test_build_startup_check_reports_missing_models_separately(self) -> None:
        config = create_default_app_config()
        config.apiKey = "sk-test"
        config.defaultTranscriptionProvider = "localFasterWhisper"

        with (
            patch("backend.app.environment_service.load_config", return_value=config),
            patch(
                "backend.app.environment_service.resolve_ffmpeg_binary",
                return_value=Path("C:/LinguaSub/runtime/ffmpeg/ffmpeg.exe"),
            ),
            patch(
                "backend.app.environment_service.get_faster_whisper_runtime_status",
                return_value=FasterWhisperRuntimeStatus(
                    available=True,
                    detectedPath="C:/LinguaSub/runtime/faster_whisper/__init__.py",
                    details="runtime ready",
                ),
            ),
            patch(
                "backend.app.environment_service.build_speech_model_statuses",
                return_value=[
                    SpeechModelStatus(
                        size="tiny",
                        label="Tiny",
                        available=False,
                        status="missing",
                        detectedPath=None,
                        statusText="missing",
                        details="not downloaded",
                        actionHint="download",
                    ),
                    SpeechModelStatus(
                        size="base",
                        label="Base",
                        available=False,
                        status="missing",
                        detectedPath=None,
                        statusText="missing",
                        details="not downloaded",
                        actionHint="download",
                    ),
                    SpeechModelStatus(
                        size="small",
                        label="Small",
                        available=False,
                        status="missing",
                        detectedPath=None,
                        statusText="missing",
                        details="not downloaded",
                        actionHint="download",
                    ),
                ],
            ),
            patch(
                "backend.app.environment_service.get_download_status",
                return_value=SpeechModelDownloadStatus(),
            ),
            patch(
                "backend.app.environment_service.get_config_path",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_recommended_release_config_path",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_default_user_data_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub"),
            ),
            patch(
                "backend.app.environment_service.get_default_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
            patch(
                "backend.app.environment_service.get_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
        ):
            report = build_startup_check()

        self.assertTrue(report.apiKeyConfigured)
        self.assertFalse(report.readyForMediaWorkflow)
        self.assertFalse(report.readyForLocalTranscription)
        self.assertTrue(
            any("No speech model files are installed yet." in warning for warning in report.warnings)
        )
        self.assertTrue(any(action.startswith("Use the Download Model action") for action in report.actions))

    def test_build_startup_check_reports_ready_media_workflow(self) -> None:
        config = create_default_app_config()
        config.apiKey = "sk-test"
        config.defaultTranscriptionProvider = "localFasterWhisper"

        with (
            patch("backend.app.environment_service.load_config", return_value=config),
            patch(
                "backend.app.environment_service.resolve_ffmpeg_binary",
                return_value=Path("C:/LinguaSub/runtime/ffmpeg/ffmpeg.exe"),
            ),
            patch(
                "backend.app.environment_service.get_faster_whisper_runtime_status",
                return_value=FasterWhisperRuntimeStatus(
                    available=True,
                    detectedPath="C:/LinguaSub/runtime/faster_whisper/__init__.py",
                    details="runtime ready",
                ),
            ),
            patch(
                "backend.app.environment_service.build_speech_model_statuses",
                return_value=[
                    SpeechModelStatus(
                        size="small",
                        label="Small",
                        available=True,
                        status="ready",
                        detectedPath="C:/Users/Test/AppData/Roaming/LinguaSub/speech-models/small",
                        statusText="installed",
                        details="ready",
                        actionHint="start recognition",
                    )
                ],
            ),
            patch(
                "backend.app.environment_service.get_download_status",
                return_value=SpeechModelDownloadStatus(),
            ),
            patch(
                "backend.app.environment_service.get_config_path",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_recommended_release_config_path",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_default_user_data_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub"),
            ),
            patch(
                "backend.app.environment_service.get_default_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
            patch(
                "backend.app.environment_service.get_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
        ):
            report = build_startup_check()

        self.assertTrue(report.apiKeyConfigured)
        self.assertTrue(report.readyForMediaWorkflow)
        self.assertTrue(report.readyForLocalTranscription)
        self.assertEqual(report.warnings, [])
        self.assertEqual(report.defaultAsrModelSize, "small")

    def test_build_startup_check_reports_ready_cloud_transcription(self) -> None:
        config = create_default_app_config()
        config.apiKey = "sk-translation"
        config.speechApiKey = "sk-speech"
        config.speechBaseUrl = "https://api.openai.com/v1"
        config.speechModel = "whisper-1"
        config.defaultTranscriptionProvider = "openaiSpeech"

        with (
            patch("backend.app.environment_service.load_config", return_value=config),
            patch(
                "backend.app.environment_service.resolve_ffmpeg_binary",
                return_value=None,
            ),
            patch(
                "backend.app.environment_service.get_faster_whisper_runtime_status",
                return_value=FasterWhisperRuntimeStatus(
                    available=False,
                    detectedPath=None,
                    details="runtime missing",
                ),
            ),
            patch(
                "backend.app.environment_service.build_speech_model_statuses",
                return_value=[],
            ),
            patch(
                "backend.app.environment_service.get_download_status",
                return_value=SpeechModelDownloadStatus(),
            ),
            patch(
                "backend.app.environment_service.get_config_path",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_recommended_release_config_path",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/app-config.json"),
            ),
            patch(
                "backend.app.environment_service.get_default_user_data_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub"),
            ),
            patch(
                "backend.app.environment_service.get_default_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
            patch(
                "backend.app.environment_service.get_model_storage_dir",
                return_value=Path("C:/Users/Test/AppData/Roaming/LinguaSub/speech-models"),
            ),
        ):
            report = build_startup_check()

        self.assertTrue(report.speechApiConfigured)
        self.assertTrue(report.readyForCloudTranscription)
        self.assertFalse(report.readyForLocalTranscription)
        self.assertTrue(report.readyForMediaWorkflow)
        self.assertFalse(any("Cloud transcription is not configured yet." in warning for warning in report.warnings))


if __name__ == "__main__":
    unittest.main()
