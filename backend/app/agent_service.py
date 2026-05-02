"""Button-style subtitle Agent services."""

from __future__ import annotations

import json
from dataclasses import dataclass
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
AGENT_MAX_CHUNK_INPUT_CHAR_COUNT = 30000
AGENT_MAX_INPUT_CHAR_COUNT = AGENT_MAX_CHUNK_INPUT_CHAR_COUNT
AGENT_MAX_CHUNK_COUNT = 10
AGENT_MAX_SEGMENT_TEXT_CHAR_COUNT = 8000
MAX_AGENT_ISSUES = 100
AGENT_QUALITY_MAX_TOKENS = 2600
AGENT_SUMMARY_MAX_TOKENS = 3600
FRIENDLY_AGENT_JSON_ERROR = (
    "The AI returned an incomplete result. Please try again, reduce subtitle length, or switch models."
)

SUBTITLE_QUALITY_SYSTEM_PROMPT = """
You are LinguaSub's subtitle quality diagnosis Agent.
Return one complete valid JSON object only. Do not include markdown, comments, explanations, or code fences.
Analyze only the subtitle segments provided by the user.
Do not rewrite subtitles and do not return modified subtitle text.
Every issue.segmentId must be one of the provided segment ids.
For each chunk, return at most 12 issues. If there are many problems, prioritize error and warning severity items.
Keep summary to 1-2 short sentences.
Keep every message and suggestion brief.
Do not copy long subtitle text into message, suggestion, summary, or diagnostics.
Do not output long explanations outside the schema.
Close every JSON object, array, and string.

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
Return one complete valid JSON object only. Do not include markdown, comments, explanations, or code fences.
Use only the provided subtitle segments. Do not invent content that is not supported by them.
Segment start/end values are milliseconds and must remain milliseconds.
For each chunk, return at most 6 chapters and at most 12 keywords.
Keep studyNotes concise and structured; do not write a long article.
Do not copy long subtitle text into any field.
All fields must be closed as valid JSON strings, arrays, and objects.

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


@dataclass(slots=True)
class AgentChunkPlan:
    chunks: list[list[dict[str, str | int]]]
    totalSegments: int
    analyzedSegments: int
    truncatedSegmentIds: list[str]


class AgentServiceError(TranslationServiceError):
    """Base error for subtitle Agent services."""


class AgentInputError(AgentServiceError):
    """Raised when the Agent request cannot be processed as user input."""


class AgentJsonParseError(TranslationParseError):
    """Raised when an Agent provider response is not valid JSON."""

    def __init__(
        self,
        *,
        provider_name: ProviderName,
        content: str,
        stage: str,
        cause: BaseException,
    ) -> None:
        self.providerName = provider_name
        self.stage = stage
        self.contentPreview = _build_content_preview(content)
        self.likelyTruncated = _looks_like_incomplete_json(content)
        self.debugMessage = (
            f"{provider_name} returned invalid Agent JSON at {stage}. "
            f"likely_truncated={self.likelyTruncated} "
            f"content_preview={self.contentPreview!r}"
        )
        super().__init__(FRIENDLY_AGENT_JSON_ERROR)
        self.__cause__ = cause


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
        max_tokens: int,
    ) -> dict[str, Any]:
        payload = self._build_payload(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
        )
        content = self._request_message_content(
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            context_label=context_label,
        )
        try:
            return self._parse_json_object(
                content,
                provider_name=provider_name,
                stage="initial",
            )
        except AgentJsonParseError as first_error:
            retry_payload = self._build_payload(
                model=model,
                system_prompt=system_prompt,
                user_prompt=self._build_json_retry_prompt(user_prompt),
                max_tokens=max_tokens,
            )
            retry_content = self._request_message_content(
                payload=retry_payload,
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                context_label=context_label,
            )
            try:
                parsed = self._parse_json_object(
                    retry_content,
                    provider_name=provider_name,
                    stage="retry",
                )
            except AgentJsonParseError as retry_error:
                retry_error.firstParseDebugMessage = first_error.debugMessage
                raise retry_error from first_error

            _attach_agent_parse_diagnostics(
                parsed,
                parse_retry_attempted=True,
                parse_retry_succeeded=True,
                first_error=first_error,
            )
            return parsed

    def _build_payload(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: dict[str, Any],
        max_tokens: int,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_prompt, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": False,
        }

    def _request_message_content(
        self,
        *,
        payload: dict[str, Any],
        api_key: str,
        base_url: str,
        timeout_seconds: int,
        context_label: str,
    ) -> str:
        response_data = self._post_json(
            url=self._build_endpoint(base_url),
            api_key=api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
            context_label=context_label,
        )
        return self._extract_message_content(response_data)

    def _build_json_retry_prompt(self, user_prompt: dict[str, Any]) -> dict[str, Any]:
        retry_prompt = dict(user_prompt)
        retry_prompt["instruction"] = (
            "Your previous response was not valid JSON. Return only one complete valid JSON object "
            "matching the required schema. Do not include markdown. Close every object, array, and string. "
            "Keep the output concise and do not copy long subtitle text."
        )
        retry_prompt["retryRules"] = [
            "Return only valid JSON.",
            "No markdown or code fences.",
            "No text before or after the JSON object.",
            "Use the same input segments and do not omit required top-level fields.",
        ]
        return retry_prompt

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
        stage: str,
    ) -> dict[str, Any]:
        prepared_content = _prepare_translation_json_content(content)
        try:
            parsed = json.loads(prepared_content.normalizedContent)
        except json.JSONDecodeError as exc:
            raise AgentJsonParseError(
                provider_name=provider_name,
                content=content,
                stage=stage,
                cause=exc,
            ) from exc

        if not isinstance(parsed, dict):
            raise AgentJsonParseError(
                provider_name=provider_name,
                content=content,
                stage=stage,
                cause=TypeError("Agent response must be a JSON object."),
            )

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
    plan = _build_compact_segment_plan(segments)
    chunk_results: list[dict[str, Any]] = []

    for chunk_index, chunk_segments in enumerate(plan.chunks):
        user_prompt = {
            "instruction": (
                "Diagnose subtitle quality for this chunk and return JSON only. "
                "Do not modify subtitles or include rewritten subtitle text. "
                "Return at most 12 issues, prioritize error and warning items, and keep all text fields short."
            ),
            "sourceLanguage": _safe_optional_string(source_language),
            "targetLanguage": _safe_optional_string(target_language),
            "bilingualMode": _safe_optional_string(bilingual_mode),
            "chunkIndex": chunk_index + 1,
            "chunkCount": len(plan.chunks),
            "segments": chunk_segments,
        }
        response_object = _request_agent_json_object(
            config=config,
            system_prompt=SUBTITLE_QUALITY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=AGENT_QUALITY_MAX_TOKENS,
        )
        chunk_results.append(
            _normalize_subtitle_quality_result(
                response_object,
                allowed_segment_ids={item["id"] for item in chunk_segments},
                segment_count=len(chunk_segments),
            )
        )

    return _merge_subtitle_quality_results(chunk_results, plan)


def summarize_subtitle_content(
    *,
    segments: list[SubtitleSegment],
    config: AppConfig,
    source_language: str | None = None,
    target_language: str | None = None,
    bilingual_mode: str | None = None,
    timeout_seconds: int | str | None = DEFAULT_AGENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    plan = _build_compact_segment_plan(segments)
    chunk_results: list[dict[str, Any]] = []

    for chunk_index, chunk_segments in enumerate(plan.chunks):
        user_prompt = {
            "instruction": (
                "Summarize this subtitle chunk and produce structured study notes. "
                "Return JSON only. Return at most 6 chapters and 12 keywords. "
                "Keep studyNotes concise and do not copy long subtitle text."
            ),
            "sourceLanguage": _safe_optional_string(source_language),
            "targetLanguage": _safe_optional_string(target_language),
            "bilingualMode": _safe_optional_string(bilingual_mode),
            "chunkIndex": chunk_index + 1,
            "chunkCount": len(plan.chunks),
            "segments": chunk_segments,
        }
        response_object = _request_agent_json_object(
            config=config,
            system_prompt=CONTENT_SUMMARY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=AGENT_SUMMARY_MAX_TOKENS,
        )
        chunk_results.append(_normalize_content_summary_result(response_object))

    return _merge_content_summary_results(chunk_results, plan)


def _request_agent_json_object(
    *,
    config: AppConfig,
    system_prompt: str,
    user_prompt: dict[str, Any],
    timeout_seconds: int | str | None,
    max_tokens: int,
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
        max_tokens=max_tokens,
        context_label=_build_agent_request_context(
            provider=provider_config.provider,
            model=provider_config.model,
            base_url=provider_config.baseUrl,
        ),
    )


def _build_compact_segments(
    segments: list[SubtitleSegment],
) -> list[dict[str, str | int]]:
    plan = _build_compact_segment_plan(segments)
    return [segment for chunk in plan.chunks for segment in chunk]


def _build_compact_segment_plan(segments: list[SubtitleSegment]) -> AgentChunkPlan:
    if not segments:
        raise AgentInputError(
            "No subtitle segments available for Agent analysis. Please transcribe or import subtitles first."
        )

    compact_segments: list[dict[str, str | int]] = []
    truncated_segment_ids: list[str] = []
    for segment in segments:
        segment_id = _safe_string(segment.id).strip()
        if not segment_id:
            raise AgentInputError(
                "Every subtitle segment must have a stable id before using the Agent."
            )

        source_text, source_truncated = _truncate_segment_text(
            _safe_string(segment.sourceText)
        )
        translated_text, translated_truncated = _truncate_segment_text(
            _safe_string(segment.translatedText)
        )
        if source_truncated or translated_truncated:
            truncated_segment_ids.append(segment_id)

        compact_segments.append(
            {
                "id": segment_id,
                "start": _safe_int(segment.start),
                "end": _safe_int(segment.end),
                "sourceText": source_text,
                "translatedText": translated_text,
            }
        )

    chunks = _chunk_compact_segments(compact_segments)
    if len(chunks) > AGENT_MAX_CHUNK_COUNT:
        raise AgentInputError(
            "Subtitle content is too long for this Agent request. "
            "Please shorten the video or split the subtitle file into smaller parts."
        )

    return AgentChunkPlan(
        chunks=chunks,
        totalSegments=len(compact_segments),
        analyzedSegments=sum(len(chunk) for chunk in chunks),
        truncatedSegmentIds=truncated_segment_ids,
    )


def _chunk_compact_segments(
    compact_segments: list[dict[str, str | int]],
) -> list[list[dict[str, str | int]]]:
    chunks: list[list[dict[str, str | int]]] = []
    current_chunk: list[dict[str, str | int]] = []

    for segment in compact_segments:
        single_segment_size = _measure_agent_segment_payload_chars([segment])
        if single_segment_size > AGENT_MAX_CHUNK_INPUT_CHAR_COUNT:
            raise AgentInputError(
                "A subtitle segment is too long for Agent analysis even after safe truncation. "
                f"segmentId={segment['id']}"
            )

        candidate_chunk = [*current_chunk, segment]
        candidate_size = _measure_agent_segment_payload_chars(candidate_chunk)
        if (
            current_chunk
            and candidate_size > AGENT_MAX_CHUNK_INPUT_CHAR_COUNT
        ):
            chunks.append(current_chunk)
            current_chunk = [segment]
            continue

        current_chunk = candidate_chunk

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _measure_agent_segment_payload_chars(
    compact_segments: list[dict[str, str | int]],
) -> int:
    return len(json.dumps({"segments": compact_segments}, ensure_ascii=False))


def _truncate_segment_text(text: str) -> tuple[str, bool]:
    if len(text) <= AGENT_MAX_SEGMENT_TEXT_CHAR_COUNT:
        return text, False

    return text[:AGENT_MAX_SEGMENT_TEXT_CHAR_COUNT], True


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
        "diagnostics": _safe_object(response_object.get("diagnostics")),
    }


def _merge_subtitle_quality_results(
    chunk_results: list[dict[str, Any]],
    plan: AgentChunkPlan,
) -> dict[str, Any]:
    if not chunk_results:
        raise TranslationParseError("Agent returned no subtitle quality results.")

    summaries: list[str] = []
    all_issues: list[dict[str, str]] = []
    filtered_segment_ids: list[str] = []
    filtered_issue_types: list[str] = []
    invalid_issue_item_count = 0
    weighted_score_total = 0

    for chunk_result, chunk_segments in zip(chunk_results, plan.chunks):
        segment_count = len(chunk_segments)
        weighted_score_total += _normalize_score(chunk_result.get("score")) * segment_count
        summary = _safe_string(chunk_result.get("summary")).strip()
        if summary:
            summaries.append(summary)
        raw_issues = chunk_result.get("issues")
        if isinstance(raw_issues, list):
            all_issues.extend(
                item for item in raw_issues if isinstance(item, dict)
            )

        diagnostics = _safe_object(chunk_result.get("diagnostics"))
        filtered_segment_ids.extend(
            _safe_string(item)
            for item in diagnostics.get("filteredIssueSegmentIds", [])
            if _safe_string(item)
        )
        filtered_issue_types.extend(
            _safe_string(item)
            for item in diagnostics.get("filteredIssueTypes", [])
            if _safe_string(item)
        )
        invalid_issue_item_count += _safe_int(
            diagnostics.get("invalidIssueItemCount", 0)
        )

    issue_limit_applied = len(all_issues) > MAX_AGENT_ISSUES
    limited_issues = all_issues[:MAX_AGENT_ISSUES]

    return {
        "score": _normalize_score(weighted_score_total / max(plan.analyzedSegments, 1)),
        "summary": _merge_quality_summaries(summaries, plan),
        "issues": limited_issues,
        "diagnostics": _build_chunk_diagnostics(
            plan,
            {
                **_collect_parse_retry_diagnostics(chunk_results),
                "issueLimit": MAX_AGENT_ISSUES,
                "issueLimitApplied": issue_limit_applied,
                "filteredIssueSegmentIds": filtered_segment_ids,
                "filteredIssueTypes": filtered_issue_types,
                "invalidIssueItemCount": invalid_issue_item_count,
                "chunkScores": [
                    _normalize_score(result.get("score")) for result in chunk_results
                ],
            },
        ),
    }


def _merge_content_summary_results(
    chunk_results: list[dict[str, Any]],
    plan: AgentChunkPlan,
) -> dict[str, Any]:
    if not chunk_results:
        raise TranslationParseError("Agent returned no content summary results.")

    if len(chunk_results) == 1:
        merged = dict(chunk_results[0])
        merged["diagnostics"] = _build_chunk_diagnostics(
            plan,
            {
                **_collect_parse_retry_diagnostics(chunk_results),
                "finalMergePerformed": False,
                "keywordDeduplicated": False,
            },
        )
        return merged

    chapters: list[dict[str, str | int]] = []
    keyword_by_term: dict[str, dict[str, str]] = {}
    one_sentence_parts: list[str] = []
    study_note_parts: list[str] = []

    for index, chunk_result in enumerate(chunk_results, start=1):
        raw_chapters = chunk_result.get("chapters", [])
        if isinstance(raw_chapters, list):
            chapters.extend(item for item in raw_chapters if isinstance(item, dict))

        raw_keywords = chunk_result.get("keywords", [])
        if isinstance(raw_keywords, list):
            for item in raw_keywords:
                if not isinstance(item, dict):
                    continue
                term = _safe_string(item.get("term")).strip()
                if not term:
                    continue
                normalized_term = term.casefold()
                if normalized_term not in keyword_by_term:
                    keyword_by_term[normalized_term] = {
                        "term": term,
                        "translation": _safe_string(item.get("translation")),
                        "explanation": _safe_string(item.get("explanation")),
                    }

        one_sentence_summary = _safe_string(
            chunk_result.get("oneSentenceSummary")
        ).strip()
        if one_sentence_summary:
            one_sentence_parts.append(one_sentence_summary)

        study_notes = _safe_string(chunk_result.get("studyNotes")).strip()
        if study_notes:
            study_note_parts.append(f"Part {index}: {study_notes}")

    return {
        "oneSentenceSummary": _merge_content_one_sentence(
            one_sentence_parts,
            plan,
        ),
        "chapters": chapters,
        "keywords": list(keyword_by_term.values()),
        "studyNotes": "\n\n".join(study_note_parts),
        "diagnostics": _build_chunk_diagnostics(
            plan,
            {
                **_collect_parse_retry_diagnostics(chunk_results),
                "finalMergePerformed": False,
                "keywordDeduplicated": True,
            },
        ),
    }


def _merge_quality_summaries(
    summaries: list[str],
    plan: AgentChunkPlan,
) -> str:
    if len(plan.chunks) == 1:
        return summaries[0] if summaries else ""

    if not summaries:
        return (
            f"Analyzed {plan.analyzedSegments} subtitle segments in "
            f"{len(plan.chunks)} chunks."
        )

    return (
        f"Analyzed {plan.analyzedSegments} subtitle segments in "
        f"{len(plan.chunks)} chunks. Main findings: "
        f"{_join_limited_texts(summaries, limit=700)}"
    )


def _merge_content_one_sentence(
    summaries: list[str],
    plan: AgentChunkPlan,
) -> str:
    if len(plan.chunks) == 1:
        return summaries[0] if summaries else ""

    if not summaries:
        return (
            f"Summarized {plan.analyzedSegments} subtitle segments across "
            f"{len(plan.chunks)} chunks."
        )

    return (
        f"Summarized {plan.analyzedSegments} subtitle segments across "
        f"{len(plan.chunks)} chunks: {_join_limited_texts(summaries, limit=500)}"
    )


def _join_limited_texts(values: list[str], *, limit: int) -> str:
    joined = " ".join(value.strip() for value in values if value.strip())
    if len(joined) <= limit:
        return joined
    return joined[:limit].rstrip() + "...(truncated)"


def _build_chunk_diagnostics(
    plan: AgentChunkPlan,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "chunked": len(plan.chunks) > 1,
        "chunkCount": len(plan.chunks),
        "totalSegments": plan.totalSegments,
        "analyzedSegments": plan.analyzedSegments,
        "maxChunkInputChars": AGENT_MAX_CHUNK_INPUT_CHAR_COUNT,
        "maxChunkCount": AGENT_MAX_CHUNK_COUNT,
        "truncated": bool(plan.truncatedSegmentIds),
        "truncatedSegmentIds": plan.truncatedSegmentIds,
    }
    if extra:
        diagnostics.update(extra)
    return diagnostics


def _collect_parse_retry_diagnostics(
    chunk_results: list[dict[str, Any]],
) -> dict[str, Any]:
    attempted_chunks: list[int] = []
    succeeded_chunks: list[int] = []
    likely_truncated_chunks: list[int] = []

    for index, chunk_result in enumerate(chunk_results, start=1):
        diagnostics = _safe_object(chunk_result.get("diagnostics"))
        if diagnostics.get("parseRetryAttempted"):
            attempted_chunks.append(index)
        if diagnostics.get("parseRetrySucceeded"):
            succeeded_chunks.append(index)
        if diagnostics.get("parseRetryLikelyTruncated"):
            likely_truncated_chunks.append(index)

    return {
        "parseRetryAttempted": bool(attempted_chunks),
        "parseRetrySucceeded": bool(attempted_chunks)
        and len(attempted_chunks) == len(succeeded_chunks),
        "parseRetryAttemptedChunks": attempted_chunks,
        "parseRetrySucceededChunks": succeeded_chunks,
        "parseRetryLikelyTruncatedChunks": likely_truncated_chunks,
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


def _attach_agent_parse_diagnostics(
    parsed: dict[str, Any],
    *,
    parse_retry_attempted: bool,
    parse_retry_succeeded: bool,
    first_error: AgentJsonParseError,
) -> None:
    diagnostics = _safe_object(parsed.get("diagnostics"))
    diagnostics.update(
        {
            "parseRetryAttempted": parse_retry_attempted,
            "parseRetrySucceeded": parse_retry_succeeded,
            "parseRetryLikelyTruncated": first_error.likelyTruncated,
            "parseRetryStage": first_error.stage,
        }
    )
    parsed["diagnostics"] = diagnostics


def _looks_like_incomplete_json(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return False

    if stripped.endswith(("...", "...(truncated)", "(truncated)")):
        return True

    if stripped.startswith("{") and not stripped.endswith("}"):
        return True
    if stripped.startswith("[") and not stripped.endswith("]"):
        return True

    return _has_unbalanced_json_delimiters(stripped)


def _has_unbalanced_json_delimiters(content: str) -> bool:
    stack: list[str] = []
    in_string = False
    escape_next = False
    pairs = {"}": "{", "]": "["}

    for char in content:
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char in "{[":
            stack.append(char)
            continue

        if char in pairs:
            if not stack or stack[-1] != pairs[char]:
                return True
            stack.pop()

    return in_string or bool(stack)


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
