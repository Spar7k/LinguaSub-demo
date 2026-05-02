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
        translated_text: str = "Hello translated",
        start: int = 1200,
        end: int = 4500,
    ) -> SubtitleSegment:
        return SubtitleSegment(
            id=segment_id,
            start=start,
            end=end,
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
        summary: str = "Overall quality is good.",
        issues: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return self.build_chat_response(
            json.dumps(
                {
                    "score": score,
                    "summary": summary,
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

    def build_summary_response(
        self,
        *,
        one_sentence: str = "The video introduces AI.",
        chapters: list[dict[str, object]] | None = None,
        keywords: list[dict[str, object]] | None = None,
        study_notes: str = "Review the key definitions.",
    ) -> dict[str, object]:
        return self.build_chat_response(
            json.dumps(
                {
                    "oneSentenceSummary": one_sentence,
                    "chapters": chapters
                    if chapters is not None
                    else [
                        {
                            "start": 0,
                            "end": 80000,
                            "title": "Introduction",
                            "summary": "The speaker introduces the topic.",
                        }
                    ],
                    "keywords": keywords
                    if keywords is not None
                    else [
                        {
                            "term": "speech recognition",
                            "translation": "ASR",
                            "explanation": "Turning speech into text.",
                        }
                    ],
                    "studyNotes": study_notes,
                },
                ensure_ascii=False,
            )
        )

    def make_long_segments(self, count: int) -> list[SubtitleSegment]:
        return [
            self.build_segment(
                f"seg-{index:03d}",
                source_text="source " + ("x" * 300),
                translated_text="translated " + ("y" * 80),
                start=index * 1000,
                end=index * 1000 + 900,
            )
            for index in range(1, count + 1)
        ]

    def extract_prompt(self, mock_post_json, call_index: int = 0) -> dict[str, object]:
        payload = mock_post_json.call_args_list[call_index].kwargs["payload"]
        return json.loads(payload["messages"][1]["content"])

    def test_agent_rejects_empty_segments(self) -> None:
        with self.assertRaises(AgentInputError):
            analyze_subtitle_quality(segments=[], config=self.build_config())

    def test_short_subtitles_do_not_trigger_chunking(self) -> None:
        segments = [self.build_segment("seg-001")]

        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_quality_response(),
        ) as mock_post_json:
            result = analyze_subtitle_quality(
                segments=segments,
                config=self.build_config(),
            )

        self.assertEqual(mock_post_json.call_count, 1)
        self.assertFalse(result["diagnostics"]["chunked"])
        self.assertEqual(result["diagnostics"]["chunkCount"], 1)
        self.assertEqual(result["diagnostics"]["totalSegments"], 1)
        self.assertEqual(result["diagnostics"]["analyzedSegments"], 1)

    def test_compact_payload_only_contains_required_segment_fields(self) -> None:
        segments = [self.build_segment("seg-001")]

        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_quality_response(),
        ) as mock_post_json:
            analyze_subtitle_quality(segments=segments, config=self.build_config())

        user_prompt = self.extract_prompt(mock_post_json)
        self.assertEqual(
            set(user_prompt["segments"][0].keys()),
            {"id", "start", "end", "sourceText", "translatedText"},
        )
        payload = mock_post_json.call_args.kwargs["payload"]
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

    def test_long_subtitles_trigger_chunking(self) -> None:
        segments = self.make_long_segments(3)

        with patch("backend.app.agent_service.AGENT_MAX_CHUNK_INPUT_CHAR_COUNT", 600):
            with patch.object(
                AgentChatCompletionClient,
                "_post_json",
                return_value=self.build_quality_response(issues=[]),
            ) as mock_post_json:
                result = analyze_subtitle_quality(
                    segments=segments,
                    config=self.build_config(),
                )

        self.assertEqual(mock_post_json.call_count, 3)
        self.assertTrue(result["diagnostics"]["chunked"])
        self.assertEqual(result["diagnostics"]["chunkCount"], 3)
        self.assertEqual(result["diagnostics"]["totalSegments"], 3)
        self.assertEqual(result["diagnostics"]["analyzedSegments"], 3)
        self.assertEqual(result["diagnostics"]["maxChunkInputChars"], 600)

    def test_chunked_quality_merges_issues(self) -> None:
        segments = self.make_long_segments(3)

        def respond_with_issue(**kwargs):
            prompt = json.loads(kwargs["payload"]["messages"][1]["content"])
            segment_id = prompt["segments"][0]["id"]
            return self.build_quality_response(
                issues=[
                    {
                        "segmentId": segment_id,
                        "severity": "warning",
                        "type": "too_long",
                        "message": f"{segment_id} is long.",
                        "suggestion": "Shorten it.",
                    }
                ]
            )

        with patch("backend.app.agent_service.AGENT_MAX_CHUNK_INPUT_CHAR_COUNT", 600):
            with patch.object(
                AgentChatCompletionClient,
                "_post_json",
                side_effect=respond_with_issue,
            ):
                result = analyze_subtitle_quality(
                    segments=segments,
                    config=self.build_config(),
                )

        self.assertEqual(
            [issue["segmentId"] for issue in result["issues"]],
            ["seg-001", "seg-002", "seg-003"],
        )
        self.assertFalse(result["diagnostics"]["issueLimitApplied"])

    def test_chunked_quality_uses_weighted_average_score(self) -> None:
        segments = self.make_long_segments(3)
        scores = iter([0, 100, 100])

        def respond_with_score(**_kwargs):
            return self.build_quality_response(score=next(scores), issues=[])

        with patch("backend.app.agent_service.AGENT_MAX_CHUNK_INPUT_CHAR_COUNT", 600):
            with patch.object(
                AgentChatCompletionClient,
                "_post_json",
                side_effect=respond_with_score,
            ):
                result = analyze_subtitle_quality(
                    segments=segments,
                    config=self.build_config(),
                )

        self.assertEqual(result["score"], 67)
        self.assertEqual(result["diagnostics"]["chunkScores"], [0, 100, 100])

    def test_chunked_content_summary_merges_chapters(self) -> None:
        segments = self.make_long_segments(3)

        def respond_with_chapter(**kwargs):
            prompt = json.loads(kwargs["payload"]["messages"][1]["content"])
            segment = prompt["segments"][0]
            return self.build_summary_response(
                one_sentence=f"Summary for {segment['id']}.",
                chapters=[
                    {
                        "start": segment["start"],
                        "end": segment["end"],
                        "title": segment["id"],
                        "summary": "Chunk summary.",
                    }
                ],
                keywords=[],
                study_notes=f"Notes for {segment['id']}.",
            )

        with patch("backend.app.agent_service.AGENT_MAX_CHUNK_INPUT_CHAR_COUNT", 600):
            with patch.object(
                AgentChatCompletionClient,
                "_post_json",
                side_effect=respond_with_chapter,
            ):
                result = summarize_subtitle_content(
                    segments=segments,
                    config=self.build_config(),
                )

        self.assertEqual(len(result["chapters"]), 3)
        self.assertEqual(result["chapters"][0]["start"], 1000)
        self.assertEqual(result["chapters"][2]["end"], 3900)
        self.assertIn("Part 1", result["studyNotes"])
        self.assertFalse(result["diagnostics"]["finalMergePerformed"])

    def test_chunked_content_summary_deduplicates_keywords(self) -> None:
        segments = self.make_long_segments(2)

        with patch("backend.app.agent_service.AGENT_MAX_CHUNK_INPUT_CHAR_COUNT", 600):
            with patch.object(
                AgentChatCompletionClient,
                "_post_json",
                return_value=self.build_summary_response(
                    keywords=[
                        {
                            "term": "Speech Recognition",
                            "translation": "ASR",
                            "explanation": "Speech to text.",
                        }
                    ],
                ),
            ):
                result = summarize_subtitle_content(
                    segments=segments,
                    config=self.build_config(),
                )

        self.assertEqual(len(result["keywords"]), 1)
        self.assertEqual(result["keywords"][0]["term"], "Speech Recognition")
        self.assertTrue(result["diagnostics"]["keywordDeduplicated"])

    def test_single_overlong_segment_is_truncated_with_diagnostics(self) -> None:
        segments = [
            self.build_segment(
                "seg-001",
                source_text="x" * 100,
                translated_text="y" * 100,
            )
        ]
        before = [segment.to_dict() for segment in segments]

        def assert_truncated_payload(**kwargs):
            prompt = json.loads(kwargs["payload"]["messages"][1]["content"])
            segment = prompt["segments"][0]
            self.assertEqual(len(segment["sourceText"]), 20)
            self.assertEqual(len(segment["translatedText"]), 20)
            return self.build_quality_response(issues=[])

        with patch("backend.app.agent_service.AGENT_MAX_SEGMENT_TEXT_CHAR_COUNT", 20):
            with patch.object(
                AgentChatCompletionClient,
                "_post_json",
                side_effect=assert_truncated_payload,
            ):
                result = analyze_subtitle_quality(
                    segments=segments,
                    config=self.build_config(),
                )

        self.assertTrue(result["diagnostics"]["truncated"])
        self.assertEqual(result["diagnostics"]["truncatedSegmentIds"], ["seg-001"])
        self.assertEqual([segment.to_dict() for segment in segments], before)

    def test_content_summary_parses_normal_json(self) -> None:
        with patch.object(
            AgentChatCompletionClient,
            "_post_json",
            return_value=self.build_summary_response(),
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
        self.assertFalse(result["diagnostics"]["chunked"])

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

        self.assertEqual(result["oneSentenceSummary"], "")
        self.assertEqual(result["chapters"], [])
        self.assertEqual(result["keywords"], [])
        self.assertEqual(result["studyNotes"], "")
        self.assertFalse(result["diagnostics"]["chunked"])

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
        segments = self.make_long_segments(3)
        before = [segment.to_dict() for segment in segments]

        with patch("backend.app.agent_service.AGENT_MAX_CHUNK_INPUT_CHAR_COUNT", 600):
            with patch.object(
                AgentChatCompletionClient,
                "_post_json",
                return_value=self.build_quality_response(issues=[]),
            ):
                analyze_subtitle_quality(segments=segments, config=self.build_config())

        self.assertEqual([segment.to_dict() for segment in segments], before)


if __name__ == "__main__":
    unittest.main()
