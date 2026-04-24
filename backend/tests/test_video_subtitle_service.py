"""Tests for the video subtitle orchestration service."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.models import SubtitleSegment, create_default_app_config
from backend.app.subtitle_alignment_service import (
    SubtitleAlignmentDiagnostics,
    SubtitleAlignmentResult,
)
from backend.app.transcription_service import (
    TranscriptionDiagnostics,
    TranscriptionResult,
)
from backend.app.translation_service import TranslationBatchResult
from backend.app.video_subtitle_service import (
    VideoSubtitleServiceError,
    run_video_subtitle,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class VideoSubtitleServiceTests(unittest.TestCase):
    def build_config(self):
        config = create_default_app_config()
        config.defaultTranscriptionProvider = "localFasterWhisper"
        config.speechProvider = "localFasterWhisper"
        config.defaultProvider = "openaiCompatible"
        config.apiKey = "sk-translate-test"
        config.baseUrl = "https://api.openai.com/v1"
        config.model = "gpt-4.1-mini"
        return config

    def build_transcription_result(
        self,
        *,
        source_language: str,
        source_text: str,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            segments=[
                SubtitleSegment(
                    id="seg-001",
                    start=0,
                    end=1200,
                    sourceText=source_text,
                    translatedText="",
                    sourceLanguage=source_language,  # type: ignore[arg-type]
                    targetLanguage="zh-CN",
                )
            ],
            sourceLanguage=source_language,  # type: ignore[arg-type]
            provider="localFasterWhisper",
            mode="local",
            model="small",
            qualityPreset="balanced",
            diagnostics=TranscriptionDiagnostics(
                provider="localFasterWhisper",
                mode="local",
                model="small",
                providerBaseUrl=None,
                qualityPreset="balanced",
                requestedLanguage="zh" if source_language == "zh-CN" else "en",
                detectedLanguage=source_language,  # type: ignore[arg-type]
                preprocessingProfile="speech-friendly mono 16 kHz PCM WAV",
                rawSegmentCount=1,
                finalSegmentCount=1,
                readabilityPasses=["cleanup"],
                notes=[],
            ),
        )

    def test_run_video_subtitle_supports_zh_single_pipeline(self) -> None:
        video_file = FIXTURE_DIR / "sample-video.mp4"
        config = self.build_config()

        with patch(
            "backend.app.video_subtitle_service.transcribe_media",
            return_value=self.build_transcription_result(
                source_language="zh-CN",
                source_text="你好，欢迎来到 LinguaSub。",
            ),
        ) as transcribe_media, patch(
            "backend.app.video_subtitle_service.parse_srt"
        ) as parse_srt, patch(
            "backend.app.video_subtitle_service.align_external_subtitles_to_reference"
        ) as align_external_subtitles, patch(
            "backend.app.video_subtitle_service.translate_segments"
        ) as translate_segments:
            result = run_video_subtitle(
                video_path=str(video_file),
                source_language="zh",
                output_mode="single",
                config=config,
            )

        transcribe_media.assert_called_once_with(
            file_path=str(video_file.resolve()),
            language="zh",
            provider="localFasterWhisper",
            config=config,
        )
        parse_srt.assert_not_called()
        align_external_subtitles.assert_not_called()
        translate_segments.assert_not_called()
        self.assertEqual(result.currentFile.mediaType, "video")
        self.assertEqual(result.count, 1)
        self.assertEqual(result.sourceLanguage, "zh-CN")
        self.assertEqual(result.outputMode, "single")
        self.assertEqual(result.pipeline, "transcribeOnly")
        self.assertIsNone(result.diagnostics.translation)
        self.assertIsNone(result.diagnostics.alignment)
        self.assertEqual(result.segments[0].sourceText, "你好，欢迎来到 LinguaSub。")

    def test_run_video_subtitle_supports_en_bilingual_pipeline_without_subtitle_input(
        self,
    ) -> None:
        video_file = FIXTURE_DIR / "sample-video.mp4"
        config = self.build_config()
        transcription_result = self.build_transcription_result(
            source_language="en",
            source_text="Hello, welcome to LinguaSub.",
        )
        translated_segments = [
            SubtitleSegment(
                id="seg-001",
                start=0,
                end=1200,
                sourceText="Hello, welcome to LinguaSub.",
                translatedText="你好，欢迎来到 LinguaSub。",
                sourceLanguage="en",
                targetLanguage="zh-CN",
            )
        ]

        with patch(
            "backend.app.video_subtitle_service.transcribe_media",
            return_value=transcription_result,
        ) as transcribe_media, patch(
            "backend.app.video_subtitle_service.parse_srt"
        ) as parse_srt, patch(
            "backend.app.video_subtitle_service.align_external_subtitles_to_reference"
        ) as align_external_subtitles, patch(
            "backend.app.video_subtitle_service.translate_segments",
            return_value=TranslationBatchResult(
                segments=translated_segments,
                provider="openaiCompatible",
                model="gpt-4.1-mini",
                baseUrl="https://api.openai.com/v1",
            ),
        ) as translate_segments:
            result = run_video_subtitle(
                video_path=str(video_file),
                subtitle_path="",
                source_language="en",
                output_mode="bilingual",
                config=config,
            )

        transcribe_media.assert_called_once_with(
            file_path=str(video_file.resolve()),
            language="en",
            provider="localFasterWhisper",
            config=config,
        )
        parse_srt.assert_not_called()
        align_external_subtitles.assert_not_called()
        translate_segments.assert_called_once_with(
            segments=transcription_result.segments,
            config=config,
            timeout_seconds=120,
        )
        self.assertEqual(result.outputMode, "bilingual")
        self.assertEqual(result.pipeline, "transcribeAndTranslate")
        self.assertEqual(result.segments[0].translatedText, "你好，欢迎来到 LinguaSub。")
        self.assertIsNotNone(result.diagnostics.translation)
        self.assertIsNone(result.diagnostics.alignment)
        self.assertEqual(result.diagnostics.translation.provider, "openaiCompatible")
        self.assertEqual(result.diagnostics.translation.model, "gpt-4.1-mini")

    def test_run_video_subtitle_enters_imported_srt_branch(self) -> None:
        video_file = FIXTURE_DIR / "sample-video.mp4"
        subtitle_file = FIXTURE_DIR / "subtitle-file.srt"
        config = self.build_config()
        transcription_result = self.build_transcription_result(
            source_language="en",
            source_text="Hello, welcome to LinguaSub.",
        )
        parsed_segments = [
            SubtitleSegment(
                id="seg-001",
                start=1000,
                end=3000,
                sourceText="Hello, everyone.",
                translatedText="",
                sourceLanguage="en",
                targetLanguage="zh-CN",
            )
        ]
        aligned_segments = [
            SubtitleSegment(
                id="seg-001",
                start=0,
                end=1200,
                sourceText="Hello, everyone.",
                translatedText="",
                sourceLanguage="en",
                targetLanguage="zh-CN",
            )
        ]
        translated_segments = [
            SubtitleSegment(
                id="seg-001",
                start=0,
                end=1200,
                sourceText="Hello, everyone.",
                translatedText="大家好。",
                sourceLanguage="en",
                targetLanguage="zh-CN",
            )
        ]

        with patch(
            "backend.app.video_subtitle_service.transcribe_media",
            return_value=transcription_result,
        ) as transcribe_media, patch(
            "backend.app.video_subtitle_service.parse_srt",
            return_value=parsed_segments,
        ) as parse_srt, patch(
            "backend.app.video_subtitle_service.align_external_subtitles_to_reference",
            return_value=SubtitleAlignmentResult(
                segments=aligned_segments,
                diagnostics=SubtitleAlignmentDiagnostics(
                    status="scaffold",
                    inputCueCount=1,
                    referenceSegmentCount=1,
                    matchedCueCount=1,
                    fallbackCueCount=0,
                    matchedWithSingleAsrCount=1,
                    matchedWithMultiAsrCount=0,
                    notes=["minimal"],
                ),
            ),
        ) as align_external_subtitles, patch(
            "backend.app.video_subtitle_service.translate_segments",
            return_value=TranslationBatchResult(
                segments=translated_segments,
                provider="openaiCompatible",
                model="gpt-4.1-mini",
                baseUrl="https://api.openai.com/v1",
            ),
        ) as translate_segments:
            result = run_video_subtitle(
                video_path=str(video_file),
                subtitle_path=str(subtitle_file),
                source_language="en",
                output_mode="bilingual",
                config=config,
            )

        transcribe_media.assert_called_once_with(
            file_path=str(video_file.resolve()),
            language="en",
            provider="localFasterWhisper",
            config=config,
        )
        parse_srt.assert_called_once_with(
            file_path=subtitle_file.resolve(),
            source_language="en",
            target_language="zh-CN",
        )
        align_external_subtitles.assert_called_once_with(
            subtitle_segments=parsed_segments,
            reference_segments=transcription_result.segments,
        )
        translate_segments.assert_called_once_with(
            segments=aligned_segments,
            config=config,
            timeout_seconds=120,
        )
        self.assertEqual(result.pipeline, "alignAndTranslate")
        self.assertEqual(result.outputMode, "bilingual")
        self.assertIsNotNone(result.diagnostics.translation)
        self.assertIsNotNone(result.diagnostics.alignment)
        self.assertEqual(result.diagnostics.alignment.matchedCueCount, 1)
        self.assertEqual(result.diagnostics.alignment.fallbackCueCount, 0)
        self.assertEqual(result.segments[0].translatedText, "大家好。")

    def test_run_video_subtitle_rejects_non_srt_subtitle_file(self) -> None:
        video_file = FIXTURE_DIR / "sample-video.mp4"

        with self.assertRaises(VideoSubtitleServiceError) as context:
            run_video_subtitle(
                video_path=str(video_file),
                subtitle_path=str(video_file),
                source_language="en",
                output_mode="bilingual",
                config=self.build_config(),
            )

        self.assertIn("只支持英文 SRT", str(context.exception))

    def test_run_video_subtitle_rejects_invalid_combo(self) -> None:
        video_file = FIXTURE_DIR / "sample-video.mp4"

        with self.assertRaises(VideoSubtitleServiceError) as context:
            run_video_subtitle(
                video_path=str(video_file),
                source_language="zh",
                output_mode="bilingual",
                config=self.build_config(),
            )

        self.assertIn("中文 + 单语", str(context.exception))
        self.assertIn("英语 + 双语", str(context.exception))

    def test_run_video_subtitle_requires_video_path(self) -> None:
        with self.assertRaises(VideoSubtitleServiceError) as context:
            run_video_subtitle(
                video_path="",
                source_language="zh",
                output_mode="single",
                config=self.build_config(),
            )

        self.assertEqual(str(context.exception), "视频文件路径不能为空。")


if __name__ == "__main__":
    unittest.main()
