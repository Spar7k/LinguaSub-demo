"""Button-style subtitle Agent services."""

from __future__ import annotations

import json
from typing import Any

from .models import AppConfig, ProviderName, SubtitleSegment
from .translation_service import (
    ChatCompletionTranslationAdapter,
    ProviderApiError,
    ProviderTimeoutError,
    TranslationParseError,
    TranslationServiceError,
    _prepare_translation_json_content,
    resolve_translation_provider_config,
)

DEFAULT_AGENT_TIMEOUT_SECONDS = 60
MIN_AGENT_TIMEOUT_SECONDS = 5
MAX_AGENT_TIMEOUT_SECONDS = 180
AGENT_MAX_INPUT_CHAR_COUNT = 30000

SUBTITLE_QUALITY_SYSTEM_PROMPT = """
You are LinguaSub's subtitle quality diagnosis Agent.
Return strict JSON only. Do not include markdown, comments, explanations, or code fences.
Analyze only the subtitle segments provided by the user.
Do not rewrite subtitles and do not return modified subtitle text.
Every issue.segmentId must be one of the provided segment ids.

Check for these issue types:
- empty_translation
- missing_translation
- timing_error
- too_long
- bilingual_format_error
- terminology_inconsistent
- unnatural_translation

Return this JSON shape:
{
  "score": 82,
  "summary": "Brief overall diagnosis.",
  "issues": [
    {
      "segmentId": "seg-001",
      "severity": "warning",
      "type": "too_long",
      "message": "Readable issue description.",
      "suggestion": "Practical editing suggestion."
    }
  ],
  "diagnostics": {}
}
severity must be one of: info, warning, error.
score must represent the overall quality from 0 to 100.
""".strip()

CONTENT_SUMMARY_SYSTEM_PROMPT = """
You are LinguaSub's video content summary and study notes Agent.
Return strict JSON only. Do not include markdown, comments, explanations, or code fences.
Use only the provided subtitle segments. Do not invent content that is not supported by them.
Segment start/end values are milliseconds and must remain milliseconds.

Return this JSON shape:
{
  "oneSentenceSummary": "A concise one-sentence summary.",
  "chapters": [
    {
      "start": 0,
      "end": 80000,
      "title": "Chapter title",
      "summary": "Chapter summary."
    }
  ],
  "keywords": [
    {
      "term": "speech recognition",
      "translation": "语音识别",
      "explanation": "Brief explanation."
    }
  ],
  "studyNotes": "Structured study notes."
}
For very short input, return concise summaries and empty arrays where appropriate.
""".strip()

VALID_ISSUE_SEVERITIES = {"info", "warning", "error"}
VALID_ISSUE_TYPES = {
    "empty_translation",
    "missing_translation",
    "timing_error",
    "too_long",
    "bilingual_format_error",
    "terminology_inconsistent",
    "unnatural_translation",
}


class AgentServiceError(TranslationServiceError):
    """Base error for subtitle Agent services."""


class AgentInputError(AgentServiceError):
    """Raised when the Agent request cannot be processed as user input."""


class AgentChatCompletionClient:
    """Small Agent wrapper around the existing translation chat transport."""

    def __init__(self, provider_name: ProviderName) -> None:
        self._transport = ChatCompletionTranslationAdapter(provider_name)

    def request_json_object(
        self,
        *,
        provider_name: ProviderName,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str,
        user_prompt: dict[str, Any],
        timeout_seconds: int,
        context_label: str,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_prompt, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "stream": False,
        }
        response_data = self._post_json(
            url=self._build_endpoint(base_url),
            api_key=api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
            context_label=context_label,
        )
        content = self._extract_message_content(response_data)
        return self._parse_json_object(content, provider_name=provider_name)

    def _build_endpoint(self, base_url: str) -> str:
        return self._transport._build_endpoint(base_url)

    def _post_json(
        self,
        *,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        context_label: str,
    ) -> dict[str, Any]:
        try:
            return self._transport._post_json(
                url=url,
                api_key=api_key,
                payload=payload,
                timeout_seconds=timeout_seconds,
                context_label=context_label,
                debug_context=None,
            )
        except ProviderApiError as exc:
            message = str(exc).replace("Translation request", "Agent request")
            raise ProviderApiError(message) from exc
        except ProviderTimeoutError as exc:
            message = str(exc).replace("Translation request", "Agent request")
            raise ProviderTimeoutError(message) from exc

    def _extract_message_content(self, response_data: dict[str, Any]) -> str:
        try:
            message = response_data["choices"][0]["message"]
            content = message.get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationParseError(
                "Agent provider response is missing message content."
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise TranslationParseError("Agent provider returned empty content.")

        return content

    def _parse_json_object(
        self,
        content: str,
        *,
        provider_name: ProviderName,
    ) -> dict[str, Any]:
        prepared_content = _prepare_translation_json_content(content)
        try:
            parsed = json.loads(prepared_content.normalizedContent)
        except json.JSONDecodeError as exc:
            raise TranslationParseError(
                f"{provider_name} returned invalid Agent JSON. "
                f"content_preview={_build_content_preview(content)!r}"
            ) from exc

        if not isinstance(parsed, dict):
            raise TranslationParseError("Agent response must be a JSON object.")

        return parsed


def analyze_subtitle_quality(
    *,
    segments: list[SubtitleSegment],
    config: AppConfig,
    source_language: str | None = None,
    target_language: str | None = None,
    bilingual_mode: str | None = None,
    timeout_seconds: int | str | None = DEFAULT_AGENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    compact_segments = _build_compact_segments(segments)
    segment_ids = {item["id"] for item in compact_segments}
    user_prompt = {
        "instruction": (
            "Diagnose subtitle quality and return JSON only. "
            "Do not modify subtitles or include rewritten subtitle text."
        ),
        "sourceLanguage": _safe_optional_string(source_language),
        "targetLanguage": _safe_optional_string(target_language),
        "bilingualMode": _safe_optional_string(bilingual_mode),
        "segments": compact_segments,
    }
    response_object = _request_agent_json_object(
        config=config,
        system_prompt=SUBTITLE_QUALITY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        timeout_seconds=timeout_seconds,
    )

    return _normalize_subtitle_quality_result(
        response_object,
        allowed_segment_ids=segment_ids,
        segment_count=len(compact_segments),
    )


def summarize_subtitle_content(
    *,
    segments: list[SubtitleSegment],
    config: AppConfig,
    source_language: str | None = None,
    target_language: str | None = None,
    bilingual_mode: str | None = None,
    timeout_seconds: int | str | None = DEFAULT_AGENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    compact_segments = _build_compact_segments(segments)
    user_prompt = {
        "instruction": (
            "Summarize the video content and produce structured study notes. "
            "Return JSON only."
        ),
        "sourceLanguage": _safe_optional_string(source_language),
        "targetLanguage": _safe_optional_string(target_language),
        "bilingualMode": _safe_optional_string(bilingual_mode),
        "segments": compact_segments,
    }
    response_object = _request_agent_json_object(
        config=config,
        system_prompt=CONTENT_SUMMARY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        timeout_seconds=timeout_seconds,
    )

    return _normalize_content_summary_result(response_object)


def _request_agent_json_object(
    *,
    config: AppConfig,
    system_prompt: str,
    user_prompt: dict[str, Any],
    timeout_seconds: int | str | None,
) -> dict[str, Any]:
    provider_config = resolve_translation_provider_config(config)
    if not provider_config.baseUrl:
        raise ProviderApiError("Agent request is missing a provider base URL.")
    if not provider_config.model:
        raise ProviderApiError("Agent request is missing a model name.")

    client = AgentChatCompletionClient(provider_config.provider)
    return client.request_json_object(
        provider_name=provider_config.provider,
        api_key=provider_config.apiKey,
        base_url=provider_config.baseUrl,
        model=provider_config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_seconds=_normalize_timeout_seconds(timeout_seconds),
        context_label=_build_agent_request_context(
            provider=provider_config.provider,
            model=provider_config.model,
            base_url=provider_config.baseUrl,
        ),
    )


def _build_compact_segments(
    segments: list[SubtitleSegment],
) -> list[dict[str, str | int]]:
    if not segments:
        raise AgentInputError(
            "No subtitle segments available for Agent analysis. Please transcribe or import subtitles first."
        )

    compact_segments: list[dict[str, str | int]] = []
    for segment in segments:
        segment_id = _safe_string(segment.id).strip()
        if not segment_id:
            raise AgentInputError(
                "Every subtitle segment must have a stable id before using the Agent."
            )

        compact_segments.append(
            {
                "id": segment_id,
                "start": _safe_int(segment.start),
                "end": _safe_int(segment.end),
                "sourceText": _safe_string(segment.sourceText),
                "translatedText": _safe_string(segment.translatedText),
            }
        )

    serialized = json.dumps({"segments": compact_segments}, ensure_ascii=False)
    if len(serialized) > AGENT_MAX_INPUT_CHAR_COUNT:
        raise AgentInputError(
            "Subtitle content is too long for the first Agent version. "
            "Please try a shorter clip or split the subtitle file before using this Agent."
        )

    return compact_segments


def _normalize_subtitle_quality_result(
    response_object: dict[str, Any],
    *,
    allowed_segment_ids: set[str],
    segment_count: int,
) -> dict[str, Any]:
    diagnostics = _safe_object(response_object.get("diagnostics"))
    filtered_segment_ids: list[str] = []
    filtered_issue_types: list[str] = []
    invalid_issue_item_count = 0

    issues: list[dict[str, str]] = []
    raw_issues = response_object.get("issues", [])
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if not isinstance(item, dict):
                invalid_issue_item_count += 1
                continue

            segment_id = _safe_string(item.get("segmentId")).strip()
            if segment_id not in allowed_segment_ids:
                filtered_segment_ids.append(segment_id or "<empty>")
                continue

            issue_type = _safe_string(item.get("type")).strip()
            if issue_type not in VALID_ISSUE_TYPES:
                filtered_issue_types.append(issue_type or "<empty>")
                continue

            severity = _safe_string(item.get("severity")).strip().lower()
            if severity not in VALID_ISSUE_SEVERITIES:
                severity = "warning"

            issues.append(
                {
                    "segmentId": segment_id,
                    "severity": severity,
                    "type": issue_type,
                    "message": _safe_string(item.get("message")),
                    "suggestion": _safe_string(item.get("suggestion")),
                }
            )
    elif raw_issues is not None:
        invalid_issue_item_count = 1

    diagnostics.update(
        {
            "segmentCount": segment_count,
            "filteredIssueSegmentIds": filtered_segment_ids,
            "filteredIssueTypes": filtered_issue_types,
            "invalidIssueItemCount": invalid_issue_item_count,
        }
    )

    return {
        "score": _normalize_score(response_object.get("score", 0)),
        "summary": _safe_string(response_object.get("summary")),
        "issues": issues,
        "diagnostics": diagnostics,
    }


def _normalize_content_summary_result(
    response_object: dict[str, Any],
) -> dict[str, Any]:
    chapters: list[dict[str, str | int]] = []
    raw_chapters = response_object.get("chapters", [])
    if isinstance(raw_chapters, list):
        for item in raw_chapters:
            if not isinstance(item, dict):
                continue
            start = max(0, _safe_int(item.get("start")))
            end = max(0, _safe_int(item.get("end")))
            if end < start:
                end = start
            chapters.append(
                {
                    "start": start,
                    "end": end,
                    "title": _safe_string(item.get("title")),
                    "summary": _safe_string(item.get("summary")),
                }
            )

    keywords: list[dict[str, str]] = []
    raw_keywords = response_object.get("keywords", [])
    if isinstance(raw_keywords, list):
        for item in raw_keywords:
            if not isinstance(item, dict):
                continue
            keywords.append(
                {
                    "term": _safe_string(item.get("term")),
                    "translation": _safe_string(item.get("translation")),
                    "explanation": _safe_string(item.get("explanation")),
                }
            )

    return {
        "oneSentenceSummary": _safe_string(
            response_object.get("oneSentenceSummary")
        ),
        "chapters": chapters,
        "keywords": keywords,
        "studyNotes": _safe_string(response_object.get("studyNotes")),
    }


def _normalize_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (OverflowError, TypeError, ValueError):
        return 0

    return max(0, min(100, score))


def _normalize_timeout_seconds(value: int | str | None) -> int:
    try:
        timeout = int(value) if value is not None else DEFAULT_AGENT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        timeout = DEFAULT_AGENT_TIMEOUT_SECONDS

    return max(MIN_AGENT_TIMEOUT_SECONDS, min(MAX_AGENT_TIMEOUT_SECONDS, timeout))


def _build_agent_request_context(
    *,
    provider: ProviderName,
    model: str,
    base_url: str,
) -> str:
    return f"provider={provider} model={model or '<missing>'} base_url={base_url or '<missing>'}"


def _safe_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_string(value).strip()
    return text or None


def _safe_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError):
        return 0


def _safe_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _build_content_preview(content: str, limit: int = 260) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "...(truncated)"


analyzeSubtitleQuality = analyze_subtitle_quality
summarizeSubtitleContent = summarize_subtitle_content

__all__ = [
    "AgentInputError",
    "AgentServiceError",
    "CONTENT_SUMMARY_SYSTEM_PROMPT",
    "SUBTITLE_QUALITY_SYSTEM_PROMPT",
    "analyzeSubtitleQuality",
    "analyze_subtitle_quality",
    "summarizeSubtitleContent",
    "summarize_subtitle_content",
]
