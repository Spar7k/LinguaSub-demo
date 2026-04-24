"""Tests for translation config validation helpers."""

from __future__ import annotations

import json
import socket
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib import error

from backend.app.models import SubtitleSegment, create_default_app_config
from backend.app.translation_service import (
    OpenAICompatibleAdapter,
    ProviderApiError,
    TranslationParseError,
    TranslationServiceError,
    translate_segments,
    validate_translation_config,
)


class FakeUrlopenResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeUrlopenResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class TranslationServiceTests(unittest.TestCase):
    def build_config(self):
        config = create_default_app_config()
        provider = next(
            item for item in config.apiProviders if item.provider == config.defaultProvider
        )
        provider.apiKey = "sk-test"
        config.apiKey = "sk-test"
        config.baseUrl = provider.baseUrl
        config.model = provider.model
        return config

    def build_segment(self, segment_id: str, source_text: str) -> SubtitleSegment:
        return SubtitleSegment(
            id=segment_id,
            start=0,
            end=1000,
            sourceText=source_text,
            translatedText="",
            sourceLanguage="en",
            targetLanguage="zh-CN",
        )

    def build_chat_response(self, translations: list[dict[str, str]]) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"translations": translations},
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

    def build_raw_chat_response(self, content: str) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": content,
                    }
                }
            ]
        }

    def extract_requested_ids(self, mock_post_json) -> list[list[str]]:
        requested_ids: list[list[str]] = []
        for call in mock_post_json.call_args_list:
            payload = call.kwargs["payload"]
            prompt = json.loads(payload["messages"][1]["content"])
            requested_ids.append([segment["id"] for segment in prompt["segments"]])
        return requested_ids

    def test_validate_translation_config_requires_api_key(self) -> None:
        config = self.build_config()
        provider = next(
            item for item in config.apiProviders if item.provider == config.defaultProvider
        )
        provider.apiKey = ""
        config.apiKey = ""

        with self.assertRaises(ProviderApiError):
            validate_translation_config(config)

    def test_validate_translation_config_returns_success_result(self) -> None:
        config = self.build_config()

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
        config = self.build_config()

        with self.assertRaises(TranslationServiceError):
            translate_segments(
                [self.build_segment("seg-001", "   ")],
                config,
            )

    def test_translate_segments_keeps_normal_batch_flow_unchanged(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value=self.build_chat_response(
                [
                    {"id": "seg-001", "translatedText": "你好。"},
                    {"id": "seg-002", "translatedText": "你好吗？"},
                ]
            ),
        ) as mock_post_json:
            result = translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 1)
        self.assertEqual(
            [segment.translatedText for segment in result.segments],
            ["你好。", "你好吗？"],
        )

    def test_translate_segments_accepts_fenced_json_content(self) -> None:
        config = self.build_config()
        segments = [self.build_segment("seg-001", "Hello.")]
        fenced_content = """```json
{"translations":[{"id":"seg-001","translatedText":"浣犲ソ銆?"}]}
```"""

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value=self.build_raw_chat_response(fenced_content),
        ):
            result = translate_segments(segments, config)

        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].translatedText, "浣犲ソ銆?")

    def test_translate_segments_accepts_json_with_leading_and_trailing_text(self) -> None:
        config = self.build_config()
        segments = [self.build_segment("seg-001", "Hello.")]
        wrapped_content = (
            "Here is the translation result.\n"
            "{\"translations\":[{\"id\":\"seg-001\",\"translatedText\":\"浣犲ソ銆?\"}]}\n"
            "Thanks."
        )

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value=self.build_raw_chat_response(wrapped_content),
        ):
            result = translate_segments(segments, config)

        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].translatedText, "浣犲ソ銆?")

    def test_translate_segments_rejects_truncated_json_without_guessing(self) -> None:
        config = self.build_config()
        segments = [self.build_segment("seg-001", "Hello.")]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value=self.build_raw_chat_response(
                '{"translations":[{"id":"seg-001","translatedText":"浣犲ソ銆?"}]'
            ),
        ) as mock_post_json:
            with self.assertRaises(TranslationParseError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 1)
        message = str(context.exception)
        self.assertIn("Translation content is not valid JSON.", message)
        self.assertIn("first_parse_expected_ids=[seg-001]", message)
        self.assertIn("first_parse_batch_size=1", message)
        self.assertIn("first_parse_content_length=", message)
        self.assertIn("first_parse_content_preview=", message)
        self.assertNotIn("retry_expected_ids=", message)

    def test_translate_segments_retries_parse_failure_with_smaller_batches(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            side_effect=[
                self.build_raw_chat_response("not valid json"),
                self.build_chat_response(
                    [{"id": "seg-001", "translatedText": "浣犲ソ銆?"}]
                ),
                self.build_chat_response(
                    [{"id": "seg-002", "translatedText": "浣犲ソ鍚楋紵"}]
                ),
            ],
        ) as mock_post_json:
            result = translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 3)
        self.assertEqual(
            self.extract_requested_ids(mock_post_json),
            [["seg-001", "seg-002"], ["seg-001"], ["seg-002"]],
        )
        self.assertEqual(
            [segment.translatedText for segment in result.segments],
            ["浣犲ソ銆?", "浣犲ソ鍚楋紵"],
        )

    def test_translate_segments_keeps_dual_diagnostics_when_parse_retry_still_fails(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            side_effect=[
                self.build_raw_chat_response("```json\nnot valid json\n```"),
                self.build_raw_chat_response('{"translations": ['),
                self.build_raw_chat_response("still not json"),
            ],
        ) as mock_post_json:
            with self.assertRaises(TranslationParseError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 3)
        message = str(context.exception)
        self.assertIn("first_parse_expected_ids=[seg-001, seg-002]", message)
        self.assertIn("first_parse_batch_size=2", message)
        self.assertIn("first_parse_content_length=", message)
        self.assertIn("first_parse_suspected_code_fence=True", message)
        self.assertIn("first_parse_content_preview=", message)
        self.assertIn("retry_expected_ids=[seg-001, seg-002]", message)
        self.assertIn("retry_batch_sizes=[1, 1]", message)
        self.assertIn("retry_content_lengths=[18, 14]", message)
        self.assertIn("retry_content_previews=", message)
        self.assertIn("retry_errors=", message)

    def test_translate_segments_retries_ssl_eof_network_error_once_and_succeeds(self) -> None:
        config = self.build_config()
        segments = [self.build_segment("seg-001", "Hello.")]

        with patch(
            "backend.app.translation_service.request.urlopen",
            side_effect=[
                error.URLError(
                    "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1081)"
                ),
                FakeUrlopenResponse(
                    self.build_chat_response(
                        [{"id": "seg-001", "translatedText": "retry-ok"}]
                    )
                ),
            ],
        ) as mock_urlopen, patch(
            "backend.app.translation_service.time.sleep"
        ) as mock_sleep:
            result = translate_segments(segments, config)

        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once()
        self.assertEqual([segment.translatedText for segment in result.segments], ["retry-ok"])

    def test_translate_segments_retries_timeout_once_and_succeeds(self) -> None:
        config = self.build_config()
        segments = [self.build_segment("seg-001", "Hello.")]

        with patch(
            "backend.app.translation_service.request.urlopen",
            side_effect=[
                socket.timeout("timed out"),
                FakeUrlopenResponse(
                    self.build_chat_response(
                        [{"id": "seg-001", "translatedText": "timeout-ok"}]
                    )
                ),
            ],
        ) as mock_urlopen, patch(
            "backend.app.translation_service.time.sleep"
        ) as mock_sleep:
            result = translate_segments(segments, config)

        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once()
        self.assertEqual(
            [segment.translatedText for segment in result.segments],
            ["timeout-ok"],
        )

    def test_translate_segments_keeps_network_diagnostics_when_retry_still_fails(self) -> None:
        config = self.build_config()
        segments = [self.build_segment("seg-001", "Hello.")]

        with patch(
            "backend.app.translation_service.request.urlopen",
            side_effect=[
                error.URLError(ConnectionResetError("connection reset by peer")),
                error.URLError(ConnectionResetError("connection reset by peer")),
            ],
        ) as mock_urlopen, patch(
            "backend.app.translation_service.time.sleep"
        ) as mock_sleep:
            with self.assertRaises(ProviderApiError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once()
        message = str(context.exception)
        self.assertIn("Translation request hit a network error while using", message)
        self.assertIn("attempt_index=2/2", message)
        self.assertIn("retry_count=1", message)
        self.assertIn("exception_type=ConnectionResetError", message)
        self.assertIn("exception_message='connection reset by peer'", message)
        self.assertIn("expected_ids=[seg-001]", message)
        self.assertIn("current_batch_size=1", message)
        self.assertIn("source_char_count=6", message)

    def test_translate_segments_does_not_retry_http_401(self) -> None:
        config = self.build_config()
        segments = [self.build_segment("seg-001", "Hello.")]
        unauthorized_error = error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error":"bad key"}'),
        )

        with patch(
            "backend.app.translation_service.request.urlopen",
            side_effect=unauthorized_error,
        ) as mock_urlopen, patch(
            "backend.app.translation_service.time.sleep"
        ) as mock_sleep:
            with self.assertRaises(ProviderApiError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()
        self.assertIn("HTTP 401", str(context.exception))
        self.assertIn("attempt_index=1/2", str(context.exception))

    def test_translate_segments_retries_missing_ids_once_and_merges_retry_result(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            side_effect=[
                self.build_chat_response(
                    [{"id": "seg-001", "translatedText": "你好。"}]
                ),
                self.build_chat_response(
                    [{"id": "seg-002", "translatedText": "你好吗？"}]
                ),
            ],
        ) as mock_post_json:
            result = translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 2)
        self.assertEqual(
            self.extract_requested_ids(mock_post_json),
            [["seg-001", "seg-002"], ["seg-002"]],
        )
        self.assertEqual(
            [segment.translatedText for segment in result.segments],
            ["你好。", "你好吗？"],
        )

    def test_translate_segments_keeps_dual_diagnostics_when_retry_still_missing(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
            self.build_segment("seg-003", "See you."),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            side_effect=[
                self.build_chat_response(
                    [{"id": "seg-001", "translatedText": "你好。"}]
                ),
                self.build_chat_response(
                    [{"id": "seg-002", "translatedText": "你好吗？"}]
                ),
            ],
        ) as mock_post_json:
            with self.assertRaises(TranslationParseError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 2)
        message = str(context.exception)
        self.assertIn("expected_ids=[seg-001, seg-002, seg-003]", message)
        self.assertIn("returned_ids=[seg-001]", message)
        self.assertIn("missing_ids=[seg-002, seg-003]", message)
        self.assertIn("retry_expected_ids=[seg-002, seg-003]", message)
        self.assertIn("retry_returned_ids=[seg-002]", message)
        self.assertIn("retry_missing_ids=[seg-003]", message)
        self.assertIn("retry_content_preview=", message)
        self.assertIn("remaining_missing_ids=[seg-003]", message)
        self.assertIn("missing translation item for segment.id='seg-003'", message)

    def test_translate_segments_retries_empty_text_ids_once_and_merges_retry_result(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            side_effect=[
                self.build_chat_response(
                    [
                        {"id": "seg-001", "translatedText": "你好。"},
                        {"id": "seg-002", "translatedText": ""},
                    ]
                ),
                self.build_chat_response(
                    [{"id": "seg-002", "translatedText": "你好吗？"}]
                ),
            ],
        ) as mock_post_json:
            result = translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 2)
        self.assertEqual(
            self.extract_requested_ids(mock_post_json),
            [["seg-001", "seg-002"], ["seg-002"]],
        )
        self.assertEqual(
            [segment.translatedText for segment in result.segments],
            ["你好。", "你好吗？"],
        )

    def test_translate_segments_keeps_dual_diagnostics_when_retry_still_empty(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            side_effect=[
                self.build_chat_response(
                    [
                        {"id": "seg-001", "translatedText": "你好。"},
                        {"id": "seg-002", "translatedText": ""},
                    ]
                ),
                self.build_chat_response(
                    [{"id": "seg-002", "translatedText": "   "}]
                ),
            ],
        ) as mock_post_json:
            with self.assertRaises(TranslationParseError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 2)
        message = str(context.exception)
        self.assertIn("empty translatedText for segment.id='seg-002'", message)
        self.assertIn("empty_text_ids=[seg-002]", message)
        self.assertIn("retry_expected_ids=[seg-002]", message)
        self.assertIn("retry_empty_text_ids=[seg-002]", message)
        self.assertIn("retry_content_preview=", message)
        self.assertIn("remaining_empty_text_ids=[seg-002]", message)

    def test_translate_segments_does_not_retry_when_first_response_has_invalid_items(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value=self.build_chat_response(
                [
                    {"id": "seg-001", "translatedText": "你好。"},
                    {"id": "seg-002"},
                ]
            ),
        ) as mock_post_json:
            with self.assertRaises(TranslationParseError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 1)
        self.assertNotIn("retry_expected_ids=", str(context.exception))
        self.assertIn("invalid translation items returned:", str(context.exception))

    def test_translate_segments_does_not_retry_when_first_response_has_unexpected_ids(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value=self.build_chat_response(
                [
                    {"id": "seg-001", "translatedText": "你好。"},
                    {"id": "seg-999", "translatedText": "额外结果"},
                ]
            ),
        ) as mock_post_json:
            with self.assertRaises(TranslationParseError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 1)
        self.assertIn("unexpected translation ids returned: [seg-999]", str(context.exception))
        self.assertNotIn("retry_expected_ids=", str(context.exception))

    def test_translate_segments_does_not_retry_empty_text_when_missing_ids_also_exist(self) -> None:
        config = self.build_config()
        segments = [
            self.build_segment("seg-001", "Hello."),
            self.build_segment("seg-002", "How are you?"),
            self.build_segment("seg-003", "See you."),
        ]

        with patch.object(
            OpenAICompatibleAdapter,
            "_post_json",
            return_value=self.build_chat_response(
                [
                    {"id": "seg-001", "translatedText": "你好。"},
                    {"id": "seg-002", "translatedText": ""},
                ]
            ),
        ) as mock_post_json:
            with self.assertRaises(TranslationParseError) as context:
                translate_segments(segments, config)

        self.assertEqual(mock_post_json.call_count, 1)
        self.assertIn("missing translation item for segment.id='seg-003'", str(context.exception))
        self.assertNotIn("retry_expected_ids=", str(context.exception))


if __name__ == "__main__":
    unittest.main()
