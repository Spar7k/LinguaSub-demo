"""Regression-oriented tests for the faster-whisper transcription pipeline."""

from __future__ import annotations

import subprocess
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.models import SubtitleSegment, create_default_app_config
from backend.app.transcription_service import (
    CloudTranscriptionConfigError,
    FfmpegNotFoundError,
    QUALITY_PROFILES,
    SpeechModelNotDownloadedError,
    UnsupportedTranscriptionMediaError,
    _SubtitlePiece,
    _apply_readability_cleanup,
    _clean_transcribed_text,
    _extract_audio_with_ffmpeg,
    transcribe_media,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class FakeWhisperModel:
    def __init__(
        self,
        language: str = "en",
        segments: list[SimpleNamespace] | None = None,
    ) -> None:
        self.language = language
        self.segments = segments or [
            SimpleNamespace(start=0.0, end=1.25, text=" Hello there. "),
            SimpleNamespace(start=1.5, end=3.0, text=" Welcome to LinguaSub. "),
        ]
        self.calls: list[dict[str, object]] = []

    def transcribe(self, audio_path: str, **kwargs: object) -> tuple[list[SimpleNamespace], SimpleNamespace]:
        self.calls.append(
            {
                "audio_path": audio_path,
                **kwargs,
            }
        )
        return self.segments, SimpleNamespace(language=self.language)


class FakeTempDirectory:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def __enter__(self) -> str:
        return str(self.directory)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class TranscriptionServiceTests(unittest.TestCase):
    def build_local_config(self):
        config = create_default_app_config()
        config.defaultTranscriptionProvider = "localFasterWhisper"
        return config

    def build_cloud_config(self):
        config = create_default_app_config()
        config.defaultTranscriptionProvider = "openaiSpeech"
        config.speechApiKey = "sk-speech-test"
        config.speechBaseUrl = "https://api.openai.com/v1"
        config.speechModel = "whisper-1"
        return config

    def build_baidu_file_async_config(self):
        config = create_default_app_config()
        config.defaultTranscriptionProvider = "baidu_file_async"
        config.speechProvider = "baidu_file_async"
        config.baiduFileAppId = "baidu-app-id"
        config.baiduFileApiKey = "baidu-api-key"
        config.baiduFileSecretKey = "baidu-secret-key"
        config.baiduFileDevPid = "15372"
        return config

    def test_transcribe_audio_returns_diagnostics_and_segments(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        fake_model = FakeWhisperModel(language="en")

        with (
            patch(
                "backend.app.transcription_service.tempfile.TemporaryDirectory",
                return_value=FakeTempDirectory(FIXTURE_DIR),
            ),
            patch(
                "backend.app.transcription_service._extract_audio_with_ffmpeg"
            ),
            patch(
                "backend.app.transcription_service._create_whisper_model",
                return_value=fake_model,
            ),
        ):
            result = transcribe_media(
                audio_file,
                model_size="small",
                provider="localFasterWhisper",
                config=self.build_local_config(),
            )

        self.assertEqual(len(result.segments), 2)
        self.assertIsInstance(result.segments[0], SubtitleSegment)
        self.assertEqual(result.segments[0].id, "seg-001")
        self.assertEqual(result.segments[0].start, 0)
        self.assertEqual(result.segments[0].end, 1250)
        self.assertEqual(result.segments[0].sourceText, "Hello there.")
        self.assertEqual(result.sourceLanguage, "en")
        self.assertEqual(result.provider, "localFasterWhisper")
        self.assertEqual(result.mode, "local")
        self.assertEqual(result.model, "small")
        self.assertEqual(result.qualityPreset, "balanced")
        self.assertEqual(result.diagnostics.rawSegmentCount, 2)
        self.assertEqual(result.diagnostics.finalSegmentCount, 2)
        self.assertEqual(result.diagnostics.preprocessingProfile, "speech-friendly mono 16 kHz PCM WAV")
        self.assertEqual(fake_model.calls[0]["language"], None)
        self.assertEqual(fake_model.calls[0]["beam_size"], 5)
        self.assertEqual(fake_model.calls[0]["best_of"], 5)
        self.assertTrue(str(fake_model.calls[0]["audio_path"]).endswith(".speech.wav"))

    def test_transcribe_media_prefers_explicit_language_and_accuracy_preset(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        fake_model = FakeWhisperModel(language="zh")

        with (
            patch(
                "backend.app.transcription_service.tempfile.TemporaryDirectory",
                return_value=FakeTempDirectory(FIXTURE_DIR),
            ),
            patch(
                "backend.app.transcription_service._extract_audio_with_ffmpeg"
            ),
            patch(
                "backend.app.transcription_service._create_whisper_model",
                return_value=fake_model,
            ),
        ):
            result = transcribe_media(
                audio_file,
                language="zh",
                model_size="small",
                quality_preset="accuracy",
                provider="localFasterWhisper",
                config=self.build_local_config(),
            )

        self.assertEqual(result.sourceLanguage, "zh-CN")
        self.assertEqual(result.qualityPreset, "accuracy")
        self.assertEqual(result.diagnostics.requestedLanguage, "zh")
        self.assertEqual(fake_model.calls[0]["language"], "zh")
        self.assertEqual(fake_model.calls[0]["beam_size"], 8)
        self.assertEqual(fake_model.calls[0]["best_of"], 8)
        self.assertTrue(fake_model.calls[0]["condition_on_previous_text"])

    def test_transcribe_video_uses_ffmpeg_audio_preparation(self) -> None:
        video_file = FIXTURE_DIR / "sample-video.mp4"
        fake_model = FakeWhisperModel(language="ja")

        with (
            patch(
                "backend.app.transcription_service.tempfile.TemporaryDirectory",
                return_value=FakeTempDirectory(FIXTURE_DIR),
            ),
            patch(
                "backend.app.transcription_service._extract_audio_with_ffmpeg"
            ) as extract_audio,
            patch(
                "backend.app.transcription_service._create_whisper_model",
                return_value=fake_model,
            ),
        ):
            result = transcribe_media(
                video_file,
                language="ja",
                model_size="small",
                provider="localFasterWhisper",
                config=self.build_local_config(),
            )

        extract_audio.assert_called_once()
        self.assertTrue(str(fake_model.calls[0]["audio_path"]).endswith("sample-video.speech.wav"))
        self.assertEqual(result.sourceLanguage, "ja")

    def test_ffmpeg_missing_raises_helpful_error(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"

        with (
            patch(
                "backend.app.transcription_service.tempfile.TemporaryDirectory",
                return_value=FakeTempDirectory(FIXTURE_DIR),
            ),
            patch(
                "backend.app.transcription_service.resolve_ffmpeg_binary",
                return_value=None,
            ),
        ):
            with self.assertRaises(FfmpegNotFoundError):
                transcribe_media(
                    audio_file,
                    provider="localFasterWhisper",
                    config=self.build_local_config(),
                )

    def test_transcribe_media_rejects_subtitle_file(self) -> None:
        subtitle_file = FIXTURE_DIR / "subtitle-file.srt"

        with self.assertRaises(UnsupportedTranscriptionMediaError):
            transcribe_media(
                subtitle_file,
                provider="localFasterWhisper",
                config=self.build_local_config(),
            )

    def test_transcribe_media_requires_downloaded_model(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"

        with (
            patch(
                "backend.app.transcription_service.tempfile.TemporaryDirectory",
                return_value=FakeTempDirectory(FIXTURE_DIR),
            ),
            patch(
                "backend.app.transcription_service._extract_audio_with_ffmpeg"
            ),
            patch(
                "backend.app.transcription_service.resolve_installed_model_path",
                return_value=None,
            ),
        ):
            with self.assertRaises(SpeechModelNotDownloadedError):
                transcribe_media(
                    audio_file,
                    model_size="small",
                    provider="localFasterWhisper",
                    config=self.build_local_config(),
                )

    def test_cloud_transcribe_audio_returns_timestamped_segments(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        cloud_response = {
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 1.25, "text": " Hello there. "},
                {"start": 1.4, "end": 3.05, "text": " Welcome to LinguaSub. "},
            ],
        }

        with patch(
            "backend.app.transcription_service._post_cloud_transcription_request",
            return_value=cloud_response,
        ) as post_request:
            result = transcribe_media(
                audio_file,
                language="en",
                provider="openaiSpeech",
                config=self.build_cloud_config(),
            )

        self.assertEqual(result.provider, "openaiSpeech")
        self.assertEqual(result.mode, "cloud")
        self.assertEqual(result.model, "whisper-1")
        self.assertEqual(result.sourceLanguage, "en")
        self.assertEqual(result.segments[0].start, 0)
        self.assertEqual(result.segments[0].end, 1250)
        self.assertEqual(result.segments[0].sourceText, "Hello there.")
        self.assertEqual(result.diagnostics.rawSegmentCount, 2)
        self.assertEqual(result.diagnostics.finalSegmentCount, 2)
        self.assertEqual(result.diagnostics.requestedLanguage, "en")
        self.assertTrue(post_request.called)
        self.assertIn("/audio/transcriptions", post_request.call_args.kwargs["url"])

    def test_cloud_transcribe_requires_api_key(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        config = self.build_cloud_config()
        config.speechApiKey = ""

        with self.assertRaises(CloudTranscriptionConfigError):
            transcribe_media(
                audio_file,
                provider="openaiSpeech",
                config=config,
            )

    def test_baidu_file_async_prefers_configured_speech_url_without_cos(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        config = self.build_baidu_file_async_config()
        config.baiduFileSpeechUrl = "https://example.com/audio.wav"
        raw_pieces = [
            SimpleNamespace(startMs=0, endMs=1200, text=" Hello there. "),
        ]

        with (
            patch(
                "backend.app.transcription_service._prepare_cloud_audio_input"
            ) as prepare_audio,
            patch(
                "backend.app.transcription_service.upload_audio_file"
            ) as upload_audio,
            patch(
                "backend.app.transcription_service.transcribe_with_baidu_file_async",
                return_value=raw_pieces,
            ) as transcribe_baidu,
        ):
            result = transcribe_media(
                audio_file,
                provider="baidu_file_async",
                config=config,
            )

        prepare_audio.assert_not_called()
        upload_audio.assert_not_called()
        transcribe_baidu.assert_called_once()
        self.assertEqual(
            transcribe_baidu.call_args.kwargs["speech_url"],
            "https://example.com/audio.wav",
        )
        self.assertEqual(result.provider, "baidu_file_async")
        self.assertEqual(result.segments[0].sourceText, "Hello there.")

    def test_baidu_file_async_falls_back_to_cos_upload_when_speech_url_missing(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        config = self.build_baidu_file_async_config()
        config.uploadCosSecretId = "cos-secret-id"
        config.uploadCosSecretKey = "cos-secret-key"
        config.uploadCosBucket = "linguasub-audio"
        config.uploadCosRegion = "ap-shanghai"
        raw_pieces = [
            SimpleNamespace(startMs=0, endMs=900, text=" Welcome back. "),
        ]

        @contextmanager
        def fake_prepare_cloud_audio_input(file_path: Path):
            yield file_path

        with (
            patch(
                "backend.app.transcription_service._prepare_cloud_audio_input",
                side_effect=fake_prepare_cloud_audio_input,
            ) as prepare_audio,
            patch(
                "backend.app.transcription_service.upload_audio_file",
                return_value="https://cos.example.com/audio.wav",
            ) as upload_audio,
            patch(
                "backend.app.transcription_service.transcribe_with_baidu_file_async",
                return_value=raw_pieces,
            ) as transcribe_baidu,
        ):
            result = transcribe_media(
                audio_file,
                provider="baidu_file_async",
                config=config,
            )

        prepare_audio.assert_called_once()
        upload_audio.assert_called_once()
        transcribe_baidu.assert_called_once()
        self.assertEqual(
            transcribe_baidu.call_args.kwargs["speech_url"],
            "https://cos.example.com/audio.wav",
        )
        self.assertEqual(result.provider, "baidu_file_async")
        self.assertEqual(result.segments[0].sourceText, "Welcome back.")

    def test_baidu_file_async_requires_public_speech_url_or_cos_config(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        config = self.build_baidu_file_async_config()

        with self.assertRaises(CloudTranscriptionConfigError) as context:
            transcribe_media(
                audio_file,
                provider="baidu_file_async",
                config=config,
            )

        self.assertIn("百度音频文件转写需要公网可访问的 baiduFileSpeechUrl", str(context.exception))
        self.assertIn("腾讯 COS 上传配置", str(context.exception))

    def test_baidu_file_async_rejects_non_http_speech_url(self) -> None:
        audio_file = FIXTURE_DIR / "sample-audio.mp3"
        config = self.build_baidu_file_async_config()
        config.baiduFileSpeechUrl = "D:\\audio\\sample.wav"

        with self.assertRaises(CloudTranscriptionConfigError) as context:
            transcribe_media(
                audio_file,
                provider="baidu_file_async",
                config=config,
            )

        self.assertIn("baiduFileSpeechUrl", str(context.exception))
        self.assertIn("http://", str(context.exception))
        self.assertIn("https://", str(context.exception))

    def test_extract_audio_uses_speech_friendly_ffmpeg_settings(self) -> None:
        captured_commands: list[list[str]] = []

        def fake_run(*args: object, **kwargs: object) -> None:
            command = list(args[0])  # type: ignore[index]
            captured_commands.append(command)

        with (
            patch(
                "backend.app.transcription_service.resolve_ffmpeg_binary",
                return_value=Path("C:/runtime/ffmpeg.exe"),
            ),
            patch(
                "backend.app.transcription_service.subprocess.run",
                side_effect=fake_run,
            ),
        ):
            _extract_audio_with_ffmpeg(Path("input.mp4"), Path("output.wav"))

        self.assertEqual(len(captured_commands), 1)
        command = captured_commands[0]
        self.assertIn("-ac", command)
        self.assertIn("-ar", command)
        self.assertIn("-c:a", command)
        self.assertIn("pcm_s16le", command)
        self.assertIn("-af", command)
        filter_value = command[command.index("-af") + 1]
        self.assertIn("highpass=f=80", filter_value)
        self.assertIn("lowpass=f=7600", filter_value)
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", filter_value)

    def test_clean_transcribed_text_normalizes_cjk_spacing(self) -> None:
        cleaned = _clean_transcribed_text("  你 好 ， 世 界  ", "zh-CN")
        self.assertEqual(cleaned, "你好，世界")

    def test_readability_cleanup_splits_long_segments(self) -> None:
        raw_pieces = [
            _SubtitlePiece(
                startMs=0,
                endMs=12000,
                text=(
                    "This is a fairly long sentence, followed by another clause, "
                    "and then a closing thought that should not stay on one subtitle line."
                ),
            )
        ]

        cleaned = _apply_readability_cleanup(
            raw_pieces,
            QUALITY_PROFILES["accuracy"],
            "en",
        )

        self.assertGreater(len(cleaned), 1)
        self.assertEqual(cleaned[0].startMs, 0)
        self.assertEqual(cleaned[-1].endMs, 12000)
        self.assertTrue(all(piece.endMs > piece.startMs for piece in cleaned))

    def test_readability_cleanup_merges_short_fragments(self) -> None:
        raw_pieces = [
            _SubtitlePiece(startMs=0, endMs=450, text="Hello"),
            _SubtitlePiece(startMs=520, endMs=1100, text="there."),
        ]

        cleaned = _apply_readability_cleanup(
            raw_pieces,
            QUALITY_PROFILES["balanced"],
            "en",
        )

        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0].text, "Hello there.")

    def test_ffmpeg_filter_fallback_retries_with_compatible_chain(self) -> None:
        captured_commands: list[list[str]] = []

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_commands.append(command)
            if len(captured_commands) == 1:
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=command,
                    stderr="No such filter: loudnorm",
                )
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch(
                "backend.app.transcription_service.resolve_ffmpeg_binary",
                return_value=Path("C:/runtime/ffmpeg.exe"),
            ),
            patch(
                "backend.app.transcription_service.subprocess.run",
                side_effect=fake_run,
            ),
        ):
            _extract_audio_with_ffmpeg(Path("input.mp4"), Path("output.wav"))

        self.assertEqual(len(captured_commands), 2)
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", captured_commands[0][captured_commands[0].index("-af") + 1])
        self.assertNotIn("loudnorm", captured_commands[1][captured_commands[1].index("-af") + 1])


if __name__ == "__main__":
    unittest.main()
