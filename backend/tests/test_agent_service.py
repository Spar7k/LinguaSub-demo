"""Tests for subtitle Agent services."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from backend.app.agent_service import (
    AgentChatCompletionClient,
    AgentInputError,
    analyze_subtitle_quality,
    summarize_subtitle_content,
)
from backend.app.models import SubtitleSegment, create_default_app_config
from backend.app.translation_service import TranslationParseError


class AgentServiceTests(unittest.TestCase):
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

    def build_segment(
        self,
        segment_id: str,
        source_text: str = "Hello everyone",
        translated_text: str = "大家好",
    ) -> SubtitleSegment:
        return SubtitleSegment(
            id=segment_id,
            start=1200,
            end=4500,
            sourceText=source_text,
            translatedText=translated_text,
            sourceLanguage="en",
            targetLanguage="zh-CN",
        )

    def build_chat_response(self, content: str) -> dict[str, object]:
        return {
            "choices": [
                {
                    "message": {
                        "content": content,
                    }
                }
            ]
        }

    def build_quality_response(
        self,
        *,
        score: object = 82,
        issues: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return self.build_chat_response(
            json.dumps(
                {
                    "score": score,
                    "summary": "Overall quality is good.",
                    "issues": issues
                    if issues is not None
                    else [
                        {
                            "segmentId": "seg-001",
                            "severity": "warning",
                            "type": "too_long",
                            "message": "This subtitle is long.",
                            "suggestion": "Shorten it for readability.",
                        }
                    ],
                    "diagnostics": {},
                },
                ensure_ascii=False,
            )
        )

    def test_agent_rejects_empty_segments(self) -> None:
        with self.assertRaises(AgentInputError):
            analyze_subtitle_quality(segments=[], config=self.build_config())

    def test_compact_payload_only_contains_required_segment_fields(self) -> None:
        segments = [self.build_segment("seg-001")]

        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_quality_response(),
        ) as mock_post_json:
            analyze_subtitle_quality(segments=segments, config=self.build_config())

        payload = mock_post_json.call_args.kwargs["payload"]
        user_prompt = json.loads(payload["messages"][1]["content"])
        self.assertEqual(
            set(user_prompt["segments"][0].keys()),
            {"id", "start", "end", "sourceText", "translatedText"},
        )
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertFalse(payload["stream"])

    def test_subtitle_quality_parses_normal_json(self) -> None:
        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_quality_response(),
        ):
            result = analyze_subtitle_quality(
                segments=[self.build_segment("seg-001")],
                config=self.build_config(),
            )

        self.assertEqual(result["score"], 82)
        self.assertEqual(result["summary"], "Overall quality is good.")
        self.assertEqual(result["issues"][0]["segmentId"], "seg-001")
        self.assertEqual(result["issues"][0]["type"], "too_long")

    def test_subtitle_quality_accepts_fenced_json(self) -> None:
        content = """```json
{
  "score": 70,
  "summary": "Needs review.",
  "issues": [],
  "diagnostics": {}
}
```"""

        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_chat_response(content),
        ):
            result = analyze_subtitle_quality(
                segments=[self.build_segment("seg-001")],
                config=self.build_config(),
            )

        self.assertEqual(result["score"], 70)
        self.assertEqual(result["issues"], [])

    def test_subtitle_quality_filters_unknown_segment_ids(self) -> None:
        issues = [
            {
                "segmentId": "seg-001",
                "severity": "warning",
                "type": "too_long",
                "message": "This subtitle is long.",
                "suggestion": "Shorten it.",
            },
            {
                "segmentId": "seg-missing",
                "severity": "error",
                "type": "empty_translation",
                "message": "Missing segment.",
                "suggestion": "Do not return this.",
            },
        ]

        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_quality_response(issues=issues),
        ):
            result = analyze_subtitle_quality(
                segments=[self.build_segment("seg-001")],
                config=self.build_config(),
            )

        self.assertEqual([issue["segmentId"] for issue in result["issues"]], ["seg-001"])
        self.assertEqual(
            result["diagnostics"]["filteredIssueSegmentIds"],
            ["seg-missing"],
        )

    def test_subtitle_quality_clamps_score_to_zero_to_one_hundred(self) -> None:
        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_quality_response(score=130),
        ):
            result = analyze_subtitle_quality(
                segments=[self.build_segment("seg-001")],
                config=self.build_config(),
            )

        self.assertEqual(result["score"], 100)

    def test_content_summary_parses_normal_json(self) -> None:
        response = self.build_chat_response(
            json.dumps(
                {
                    "oneSentenceSummary": "The video introduces AI.",
                    "chapters": [
                        {
                            "start": 0,
                            "end": 80000,
                            "title": "Introduction",
                            "summary": "The speaker introduces the topic.",
                        }
                    ],
                    "keywords": [
                        {
                            "term": "speech recognition",
                            "translation": "语音识别",
                            "explanation": "Turning speech into text.",
                        }
                    ],
                    "studyNotes": "Review the key definitions.",
                },
                ensure_ascii=False,
            )
        )

        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=response,
        ):
            result = summarize_subtitle_content(
                segments=[self.build_segment("seg-001")],
                config=self.build_config(),
            )

        self.assertEqual(result["oneSentenceSummary"], "The video introduces AI.")
        self.assertEqual(result["chapters"][0]["start"], 0)
        self.assertEqual(result["chapters"][0]["end"], 80000)
        self.assertEqual(result["keywords"][0]["term"], "speech recognition")
        self.assertEqual(result["studyNotes"], "Review the key definitions.")

    def test_content_summary_uses_safe_defaults_for_missing_fields(self) -> None:
        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_chat_response("{}"),
        ):
            result = summarize_subtitle_content(
                segments=[self.build_segment("seg-001")],
                config=self.build_config(),
            )

        self.assertEqual(
            result,
            {
                "oneSentenceSummary": "",
                "chapters": [],
                "keywords": [],
                "studyNotes": "",
            },
        )

    def test_invalid_agent_json_raises_clear_parse_error(self) -> None:
        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_chat_response("not json"),
        ):
            with self.assertRaises(TranslationParseError) as context:
                summarize_subtitle_content(
                    segments=[self.build_segment("seg-001")],
                    config=self.build_config(),
                )

        self.assertIn("invalid Agent JSON", str(context.exception))

    def test_agent_does_not_modify_input_segments(self) -> None:
        segments = [self.build_segment("seg-001")]
        before = [segment.to_dict() for segment in segments]

        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_quality_response(),
        ):
            analyze_subtitle_quality(segments=segments, config=self.build_config())

        self.assertEqual([segment.to_dict() for segment in segments], before)


if __name__ == "__main__":
    unittest.main()
