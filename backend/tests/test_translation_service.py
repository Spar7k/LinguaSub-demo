"""Tests for translation config validation helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.models import create_default_app_config
from backend.app.translation_service import (
    OpenAICompatibleAdapter,
    ProviderApiError,
    TranslationServiceError,
    translate_segments,
    validate_translation_config,
)
from backend.app.models import SubtitleSegment


class TranslationServiceTests(unittest.TestCase):
    def test_validate_translation_config_requires_api_key(self) -> None:
        config = create_default_app_config()
        config.apiKey = ""

        with self.assertRaises(ProviderApiError):
            validate_translation_config(config)

    def test_validate_translation_config_returns_success_result(self) -> None:
        config = create_default_app_config()
        config.apiKey = "sk-test"
        config.baseUrl = "https://api.openai.com/v1"
        config.model = "gpt-4.1-mini"

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value={"choices": [{"message": {"content": "OK"}}]},
        ):
            result = validate_translation_config(config)

        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "openaiCompatible")
        self.assertEqual(result.model, "gpt-4.1-mini")
        self.assertEqual(result.baseUrl, "https://api.openai.com/v1")
        self.assertIn("connection succeeded", result.message)

    def test_translate_segments_rejects_empty_source_text(self) -> None:
        config = create_default_app_config()
        config.apiKey = "sk-test"

        with self.assertRaises(TranslationServiceError):
            translate_segments(
                [
                    SubtitleSegment(
                        id="seg-001",
                        start=0,
                        end=1000,
                        sourceText="   ",
                        translatedText="",
                        sourceLanguage="en",
                        targetLanguage="zh-CN",
                    )
                ],
                config,
            )


if __name__ == "__main__":
    unittest.main()
