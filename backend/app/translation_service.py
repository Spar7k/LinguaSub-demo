"""Translation service with provider adapters."""

from __future__ import annotations

import json
import socket
import time
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from .config_service import get_active_provider_config, sync_active_provider_fields
from .models import AppConfig, ProviderName, SubtitleSegment

DEFAULT_TIMEOUT_SECONDS = 40
DEFAULT_BATCH_SIZE = 20
DEFAULT_CHAR_LIMIT = 2800
NETWORK_RETRY_LIMIT = 1
NETWORK_RETRY_BACKOFF_SECONDS = 0.35

SYSTEM_PROMPT = """
You are a subtitle translation assistant.
Return valid json only.
Translate each subtitle segment while preserving the original meaning.
Keep the translation concise, natural, and suitable for subtitles.
Do not add explanations, notes, speaker labels, or extra formatting.
Keep subtitle length moderate so it stays readable on screen.
Return this JSON shape exactly:
{
  "translations": [
    {
      "id": "seg-001",
      "translatedText": "example translation"
    }
  ]
}
""".strip()


class TranslationServiceError(RuntimeError):
    """Base error for the translation layer."""


class ProviderTimeoutError(TranslationServiceError):
    """Raised when a provider request times out."""


class ProviderApiError(TranslationServiceError):
    """Raised when a provider returns an API error."""


class TranslationParseError(TranslationServiceError):
    """Raised when the provider response cannot be parsed safely."""


def _validate_segments_for_translation(segments: list[SubtitleSegment]) -> None:
    for segment in segments:
        if not segment.id.strip():
            raise TranslationServiceError(
                "Every subtitle segment must have a stable id before translation."
            )
        if not segment.sourceText.strip():
            raise TranslationServiceError(
                f"Subtitle segment '{segment.id}' has empty source text. Edit the line before translating."
            )


@dataclass(slots=True)
class TranslationBatchResult:
    segments: list[SubtitleSegment]
    provider: ProviderName
    model: str
    baseUrl: str


@dataclass(slots=True)
class TranslationConfigValidationResult:
    ok: bool
    provider: ProviderName
    model: str
    baseUrl: str
    message: str


@dataclass(slots=True)
class ResolvedTranslationProviderConfig:
    provider: ProviderName
    displayName: str
    apiKey: str
    baseUrl: str
    model: str


@dataclass(slots=True)
class ParsedTranslationContent:
    translatedById: dict[str, str]
    returnedIds: list[str]
    emptyTextIds: list[str]
    invalidItems: list[str]


@dataclass(slots=True)
class PreparedTranslationJsonContent:
    normalizedContent: str
    suspectedCodeFence: bool
    extractedOuterJson: bool


@dataclass(slots=True)
class TranslationBatchAttemptResult:
    translatedById: dict[str, str]
    expectedIds: list[str]
    returnedIds: list[str]
    missingIds: list[str]
    emptyTextIds: list[str]
    unexpectedIds: list[str]
    invalidItems: list[str]
    contentPreview: str
    contentLength: int
    batchSize: int
    suspectedCodeFence: bool
    parseError: str | None = None


@dataclass(slots=True)
class TranslationRequestDebugContext:
    expectedIds: list[str]
    batchSize: int
    sourceCharCount: int


def _summarize_values(values: list[str], limit: int = 12) -> str:
    if not values:
        return "[]"

    normalized = [item for item in values if item]
    if not normalized:
        return "[]"

    if len(normalized) <= limit:
        return "[" + ", ".join(normalized) + "]"

    preview = ", ".join(normalized[:limit])
    remaining = len(normalized) - limit
    return "[" + preview + f", ... (+{remaining} more)]"


def _build_content_preview(content: str, limit: int = 260) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "...(truncated)"


def _build_source_char_count(segments: list[SubtitleSegment]) -> int:
    return sum(len(segment.sourceText) for segment in segments)


def _looks_like_code_fence(content: str) -> bool:
    return content.strip().startswith("```")


def _strip_code_fence(content: str) -> tuple[str, bool]:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped, False

    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped, False

    opening_line = lines[0].strip()
    closing_line = lines[-1].strip()
    if not opening_line.startswith("```") or closing_line != "```":
        return stripped, False

    return "\n".join(lines[1:-1]).strip(), True


def _extract_outer_json_candidate(content: str) -> tuple[str, bool]:
    stripped = content.strip()
    if not stripped:
        return stripped, False

    if (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        return stripped, False

    candidates: list[tuple[int, int, str]] = []
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start_index = stripped.find(open_char)
        end_index = stripped.rfind(close_char)
        if start_index == -1 or end_index == -1 or end_index <= start_index:
            continue
        candidates.append(
            (
                start_index,
                end_index,
                stripped[start_index : end_index + 1].strip(),
            )
        )

    if not candidates:
        return stripped, False

    start_index, end_index, candidate = min(
        candidates,
        key=lambda item: (item[0], -(item[1] - item[0])),
    )
    if stripped[:start_index].strip() or stripped[end_index + 1 :].strip():
        return candidate, True

    return stripped, False


def _prepare_translation_json_content(content: str) -> PreparedTranslationJsonContent:
    stripped = content.strip()
    unfenced_content, stripped_code_fence = _strip_code_fence(stripped)
    extracted_content, extracted_outer_json = _extract_outer_json_candidate(
        unfenced_content,
    )
    return PreparedTranslationJsonContent(
        normalizedContent=extracted_content.strip(),
        suspectedCodeFence=_looks_like_code_fence(content) or stripped_code_fence,
        extractedOuterJson=extracted_outer_json,
    )


def _is_timeout_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True

    if isinstance(exc, error.URLError):
        return isinstance(exc.reason, (socket.timeout, TimeoutError))

    return False


def _normalize_transport_error_message(message: str) -> str:
    return " ".join(message.lower().replace("_", " ").split())


def _is_retryable_transport_error(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            socket.timeout,
            TimeoutError,
            ConnectionResetError,
            ConnectionAbortedError,
            BrokenPipeError,
        ),
    ):
        return True

    if isinstance(exc, error.URLError):
        reason = exc.reason
        if isinstance(
            reason,
            (
                socket.timeout,
                TimeoutError,
                ConnectionResetError,
                ConnectionAbortedError,
                BrokenPipeError,
            ),
        ):
            return True
        message = str(reason)
    else:
        message = str(exc)

    normalized_message = _normalize_transport_error_message(message)
    retryable_markers = (
        "unexpected eof while reading",
        "eof occurred in violation of protocol",
        "connection reset",
        "connection aborted",
        "broken pipe",
        "connection closed unexpectedly",
        "remote end closed connection without response",
        "connection was closed",
        "connection reset by peer",
    )
    return any(marker in normalized_message for marker in retryable_markers)


def _describe_transport_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return reason.__class__.__name__, str(reason)
        return exc.__class__.__name__, str(reason)

    return exc.__class__.__name__, str(exc)


def _build_transport_error_suffix(
    *,
    debug_context: TranslationRequestDebugContext | None,
    attempt_index: int,
    max_attempts: int,
    exc: BaseException,
) -> str:
    exception_type, exception_message = _describe_transport_error(exc)
    retry_count = max(0, attempt_index - 1)
    suffix = (
        f" attempt_index={attempt_index}/{max_attempts}"
        f" retry_count={retry_count}"
        f" exception_type={exception_type}"
        f" exception_message={exception_message!r}"
    )
    if debug_context is not None:
        suffix += (
            f" current_batch_size={debug_context.batchSize}"
            f" expected_ids={_summarize_values(debug_context.expectedIds)}"
            f" source_char_count={debug_context.sourceCharCount}"
        )
    return suffix


class TranslationProviderAdapter(ABC):
    """Adapter base class so more providers can be added later."""

    provider_name: ProviderName

    @abstractmethod
    def translate_batch(
        self,
        segments: list[SubtitleSegment],
        config: AppConfig,
        timeout_seconds: int,
    ) -> list[SubtitleSegment]:
        raise NotImplementedError

    @abstractmethod
    def validate_connection(
        self,
        config: AppConfig,
        timeout_seconds: int,
    ) -> TranslationConfigValidationResult:
        raise NotImplementedError


def resolve_translation_provider_config(
    config: AppConfig,
) -> ResolvedTranslationProviderConfig:
    synced_config = sync_active_provider_fields(config)
    provider_config = get_active_provider_config(synced_config)

    return ResolvedTranslationProviderConfig(
        provider=synced_config.defaultProvider,
        displayName=provider_config.displayName,
        apiKey=provider_config.apiKey,
        baseUrl=provider_config.baseUrl.strip(),
        model=provider_config.model.strip(),
    )


def _build_translation_request_context(
    resolved_config: ResolvedTranslationProviderConfig,
) -> str:
    return (
        f"provider={resolved_config.provider} "
        f"model={resolved_config.model or '<missing>'} "
        f"base_url={resolved_config.baseUrl or '<missing>'}"
    )


class ChatCompletionTranslationAdapter(TranslationProviderAdapter):
    """Shared implementation for OpenAI-compatible chat completion APIs."""

    def __init__(self, provider_name: ProviderName) -> None:
        self.provider_name = provider_name

    def translate_batch(
        self,
        segments: list[SubtitleSegment],
        config: AppConfig,
        timeout_seconds: int,
    ) -> list[SubtitleSegment]:
        if not segments:
            return []

        provider_config = resolve_translation_provider_config(config)
        first_attempt = self._request_translation_attempt(
            segments=segments,
            provider_config=provider_config,
            timeout_seconds=timeout_seconds,
        )
        if first_attempt.parseError is None:
            return self._resolve_translated_segments_from_attempt(
                segments=segments,
                provider_config=provider_config,
                timeout_seconds=timeout_seconds,
                first_attempt=first_attempt,
            )

        if not self._should_retry_parse_failure(first_attempt, segments):
            raise self._build_translation_parse_failure_error(
                first_attempt=first_attempt,
                provider_config=provider_config,
                retry_attempts=[],
                retry_errors=[],
            )

        retry_attempts: list[TranslationBatchAttemptResult] = []
        retry_errors: list[str] = []
        translated_segments: list[SubtitleSegment] = []

        for retry_batch in self._split_parse_retry_batches(segments):
            retry_attempt = self._request_translation_attempt(
                segments=retry_batch,
                provider_config=provider_config,
                timeout_seconds=timeout_seconds,
            )
            retry_attempts.append(retry_attempt)

            if retry_attempt.parseError is not None:
                retry_errors.append(retry_attempt.parseError)
                continue

            try:
                translated_segments.extend(
                    self._resolve_translated_segments_from_attempt(
                        segments=retry_batch,
                        provider_config=provider_config,
                        timeout_seconds=timeout_seconds,
                        first_attempt=retry_attempt,
                    )
                )
            except TranslationParseError as exc:
                retry_errors.append(str(exc))

        if not retry_errors and len(translated_segments) == len(segments):
            return translated_segments

        raise self._build_translation_parse_failure_error(
            first_attempt=first_attempt,
            provider_config=provider_config,
            retry_attempts=retry_attempts,
            retry_errors=retry_errors,
        )

    def _resolve_translated_segments_from_attempt(
        self,
        segments: list[SubtitleSegment],
        provider_config: ResolvedTranslationProviderConfig,
        timeout_seconds: int,
        first_attempt: TranslationBatchAttemptResult,
    ) -> list[SubtitleSegment]:
        merged_translated_by_id = dict(first_attempt.translatedById)
        retry_attempt: TranslationBatchAttemptResult | None = None

        if self._should_retry_missing_only(first_attempt):
            missing_id_set = set(first_attempt.missingIds)
            retry_segments = [
                segment for segment in segments if segment.id in missing_id_set
            ]
            retry_attempt = self._request_translation_attempt(
                segments=retry_segments,
                provider_config=provider_config,
                timeout_seconds=timeout_seconds,
            )
            for segment_id, translated_text in retry_attempt.translatedById.items():
                if segment_id in missing_id_set:
                    merged_translated_by_id[segment_id] = translated_text
        elif self._should_retry_empty_text_only(first_attempt):
            empty_text_id_set = set(first_attempt.emptyTextIds)
            retry_segments = [
                segment for segment in segments if segment.id in empty_text_id_set
            ]
            retry_attempt = self._request_translation_attempt(
                segments=retry_segments,
                provider_config=provider_config,
                timeout_seconds=timeout_seconds,
            )
            for segment_id, translated_text in retry_attempt.translatedById.items():
                if segment_id in empty_text_id_set and translated_text.strip():
                    merged_translated_by_id[segment_id] = translated_text

        translated_segments: list[SubtitleSegment] = []
        remaining_missing_ids: list[str] = []
        remaining_empty_text_ids: list[str] = []
        for segment in segments:
            translated_text = merged_translated_by_id.get(segment.id)
            if translated_text is None:
                remaining_missing_ids.append(segment.id)
                continue
            if not translated_text.strip():
                remaining_empty_text_ids.append(segment.id)
                continue

            updated_segment = deepcopy(segment)
            updated_segment.translatedText = translated_text.strip()
            translated_segments.append(updated_segment)

        if (
            remaining_missing_ids
            or remaining_empty_text_ids
            or first_attempt.unexpectedIds
            or first_attempt.invalidItems
            or (
                retry_attempt is not None
                and (
                    retry_attempt.emptyTextIds
                    or retry_attempt.unexpectedIds
                    or retry_attempt.invalidItems
                    or retry_attempt.missingIds
                    or retry_attempt.parseError is not None
                )
            )
        ):
            raise self._build_translation_batch_error(
                first_attempt=first_attempt,
                retry_attempt=retry_attempt,
                remaining_missing_ids=remaining_missing_ids,
                remaining_empty_text_ids=remaining_empty_text_ids,
            )

        return translated_segments

    def _should_retry_parse_failure(
        self,
        attempt: TranslationBatchAttemptResult,
        segments: list[SubtitleSegment],
    ) -> bool:
        return attempt.parseError is not None and len(segments) > 1

    def _split_parse_retry_batches(
        self,
        segments: list[SubtitleSegment],
    ) -> list[list[SubtitleSegment]]:
        midpoint = max(1, len(segments) // 2)
        retry_batches = [segments[:midpoint], segments[midpoint:]]
        return [batch for batch in retry_batches if batch]

    def _build_translation_parse_failure_error(
        self,
        first_attempt: TranslationBatchAttemptResult,
        provider_config: ResolvedTranslationProviderConfig,
        retry_attempts: list[TranslationBatchAttemptResult],
        retry_errors: list[str],
    ) -> TranslationParseError:
        retry_expected_ids = [
            segment_id
            for attempt in retry_attempts
            for segment_id in attempt.expectedIds
        ]
        retry_batch_sizes = ", ".join(str(attempt.batchSize) for attempt in retry_attempts)
        retry_content_lengths = ", ".join(
            str(attempt.contentLength) for attempt in retry_attempts
        )
        retry_code_fence_flags = ", ".join(
            "true" if attempt.suspectedCodeFence else "false"
            for attempt in retry_attempts
        )
        retry_content_previews = " | ".join(
            f"batch{index + 1}:{attempt.contentPreview!r}"
            for index, attempt in enumerate(retry_attempts)
        )

        message = (
            f"{first_attempt.parseError or 'Translation content could not be parsed.'} "
            f"while using {_build_translation_request_context(provider_config)}."
            + f" first_parse_expected_ids={_summarize_values(first_attempt.expectedIds)}"
            + f" first_parse_batch_size={first_attempt.batchSize}"
            + f" first_parse_content_length={first_attempt.contentLength}"
            + (
                f" first_parse_suspected_code_fence={first_attempt.suspectedCodeFence}"
            )
            + f" first_parse_content_preview={first_attempt.contentPreview!r}"
        )

        if retry_attempts:
            message += (
                f" retry_expected_ids={_summarize_values(retry_expected_ids)}"
                + f" retry_batch_sizes=[{retry_batch_sizes}]"
                + f" retry_content_lengths=[{retry_content_lengths}]"
                + f" retry_suspected_code_fence=[{retry_code_fence_flags}]"
                + f" retry_content_previews={retry_content_previews!r}"
            )

        if retry_errors:
            message += f" retry_errors={_summarize_values(retry_errors, limit=6)}"

        return TranslationParseError(message)

    def validate_connection(
        self,
        config: AppConfig,
        timeout_seconds: int,
    ) -> TranslationConfigValidationResult:
        provider_config = resolve_translation_provider_config(config)

        if not provider_config.apiKey.strip():
            raise ProviderApiError(
                f"Translation config is missing an API key while using "
                f"{_build_translation_request_context(provider_config)}."
            )

        if not provider_config.baseUrl.strip():
            raise ProviderApiError(
                f"Translation config is missing a base URL while using "
                f"{_build_translation_request_context(provider_config)}."
            )

        if not provider_config.model.strip():
            raise ProviderApiError(
                f"Translation config is missing a model name while using "
                f"{_build_translation_request_context(provider_config)}."
            )

        payload = self._build_validation_payload(provider_config.model)
        response_data = self._post_json(
            url=self._build_endpoint(provider_config.baseUrl),
            api_key=provider_config.apiKey,
            payload=payload,
            timeout_seconds=timeout_seconds,
            context_label=_build_translation_request_context(provider_config),
        )
        self._extract_message_content(response_data)

        return TranslationConfigValidationResult(
            ok=True,
            provider=self.provider_name,
            model=provider_config.model,
            baseUrl=provider_config.baseUrl,
            message=(
                f"{provider_config.displayName} connection succeeded. "
                f"Ready for translation with model '{provider_config.model}' via "
                f"'{provider_config.baseUrl}'."
            ),
        )

    def _build_endpoint(self, base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized

        return f"{normalized}/chat/completions"

    def _build_payload(self, segments: list[SubtitleSegment], model: str) -> dict[str, Any]:
        request_segments = [
            {
                "id": segment.id,
                "sourceText": segment.sourceText,
                "sourceLanguage": segment.sourceLanguage,
                "targetLanguage": segment.targetLanguage,
            }
            for segment in segments
        ]

        user_prompt = {
            "instruction": (
                "Translate every segment and return json only. "
                "Do not include any text outside the json object."
            ),
            "segments": request_segments,
        }

        return {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_prompt, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "stream": False,
        }

    def _request_translation_attempt(
        self,
        segments: list[SubtitleSegment],
        provider_config: ResolvedTranslationProviderConfig,
        timeout_seconds: int,
    ) -> TranslationBatchAttemptResult:
        expected_ids = [segment.id for segment in segments]
        debug_context = TranslationRequestDebugContext(
            expectedIds=expected_ids,
            batchSize=len(segments),
            sourceCharCount=_build_source_char_count(segments),
        )
        payload = self._build_payload(segments, provider_config.model)
        response_data = self._post_json(
            url=self._build_endpoint(provider_config.baseUrl),
            api_key=provider_config.apiKey,
            payload=payload,
            timeout_seconds=timeout_seconds,
            context_label=_build_translation_request_context(provider_config),
            debug_context=debug_context,
        )
        content = self._extract_message_content(response_data)
        prepared_content = _prepare_translation_json_content(content)
        try:
            parsed_content = self._parse_translation_json(
                content,
                prepared_content=prepared_content,
            )
        except TranslationParseError as exc:
            return TranslationBatchAttemptResult(
                translatedById={},
                expectedIds=expected_ids,
                returnedIds=[],
                missingIds=[],
                emptyTextIds=[],
                unexpectedIds=[],
                invalidItems=[],
                contentPreview=_build_content_preview(content),
                contentLength=len(content),
                batchSize=len(segments),
                suspectedCodeFence=prepared_content.suspectedCodeFence,
                parseError=str(exc),
            )

        expected_id_set = set(expected_ids)
        returned_ids = parsed_content.returnedIds
        returned_id_set = set(returned_ids)
        empty_text_ids = [
            segment_id
            for segment_id in parsed_content.emptyTextIds
            if segment_id in expected_id_set
        ]
        missing_ids = [
            segment_id for segment_id in expected_ids if segment_id not in returned_id_set
        ]
        unexpected_ids = [
            segment_id for segment_id in returned_ids if segment_id not in expected_id_set
        ]

        return TranslationBatchAttemptResult(
            translatedById=parsed_content.translatedById,
            expectedIds=expected_ids,
            returnedIds=returned_ids,
            missingIds=missing_ids,
            emptyTextIds=empty_text_ids,
            unexpectedIds=unexpected_ids,
            invalidItems=parsed_content.invalidItems,
            contentPreview=_build_content_preview(content),
            contentLength=len(content),
            batchSize=len(segments),
            suspectedCodeFence=prepared_content.suspectedCodeFence,
        )

    def _should_retry_missing_only(
        self,
        attempt: TranslationBatchAttemptResult,
    ) -> bool:
        return bool(attempt.missingIds) and not (
            attempt.emptyTextIds
            or attempt.unexpectedIds
            or attempt.invalidItems
        )

    def _should_retry_empty_text_only(
        self,
        attempt: TranslationBatchAttemptResult,
    ) -> bool:
        return bool(attempt.emptyTextIds) and not (
            attempt.missingIds
            or attempt.unexpectedIds
            or attempt.invalidItems
        )

    def _build_translation_batch_error(
        self,
        first_attempt: TranslationBatchAttemptResult,
        remaining_missing_ids: list[str],
        remaining_empty_text_ids: list[str],
        retry_attempt: TranslationBatchAttemptResult | None = None,
    ) -> TranslationParseError:
        if first_attempt.invalidItems:
            primary_reason = (
                "Translation batch returned incomplete or invalid items."
                f" invalid translation items returned: {_summarize_values(first_attempt.invalidItems)}."
            )
        elif first_attempt.unexpectedIds:
            primary_reason = (
                "Translation batch returned incomplete or invalid items."
                f" unexpected translation ids returned: {_summarize_values(first_attempt.unexpectedIds)}."
            )
        elif remaining_missing_ids or first_attempt.missingIds:
            primary_segment_id = (
                remaining_missing_ids[0]
                if remaining_missing_ids
                else first_attempt.missingIds[0]
            )
            primary_reason = (
                "Translation batch returned incomplete or invalid items."
                f" missing translation item for segment.id='{primary_segment_id}'."
            )
        elif remaining_empty_text_ids or first_attempt.emptyTextIds:
            primary_segment_id = (
                remaining_empty_text_ids[0]
                if remaining_empty_text_ids
                else first_attempt.emptyTextIds[0]
            )
            primary_reason = (
                "Translation batch returned incomplete or invalid items."
                f" empty translatedText for segment.id='{primary_segment_id}'."
            )
        else:
            primary_reason = "Translation batch returned incomplete or invalid items."

        message = (
            primary_reason
            + f" expected_ids={_summarize_values(first_attempt.expectedIds)}"
            + f" returned_ids={_summarize_values(first_attempt.returnedIds)}"
            + f" missing_ids={_summarize_values(first_attempt.missingIds)}"
            + f" empty_text_ids={_summarize_values(first_attempt.emptyTextIds)}"
            + f" unexpected_ids={_summarize_values(first_attempt.unexpectedIds)}"
            + f" invalid_items={_summarize_values(first_attempt.invalidItems)}"
            + f" content_preview={first_attempt.contentPreview!r}"
        )

        if retry_attempt is not None:
            message += (
                f" retry_expected_ids={_summarize_values(retry_attempt.expectedIds)}"
                f" retry_returned_ids={_summarize_values(retry_attempt.returnedIds)}"
                f" retry_missing_ids={_summarize_values(retry_attempt.missingIds)}"
                f" retry_empty_text_ids={_summarize_values(retry_attempt.emptyTextIds)}"
                f" retry_unexpected_ids={_summarize_values(retry_attempt.unexpectedIds)}"
                f" retry_invalid_items={_summarize_values(retry_attempt.invalidItems)}"
                f" retry_content_preview={retry_attempt.contentPreview!r}"
            )

        if remaining_missing_ids:
            message += f" remaining_missing_ids={_summarize_values(remaining_missing_ids)}"
        if remaining_empty_text_ids:
            message += (
                f" remaining_empty_text_ids={_summarize_values(remaining_empty_text_ids)}"
            )

        return TranslationParseError(message)

    def _build_validation_payload(self, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Reply with OK only.",
                },
                {
                    "role": "user",
                    "content": "Connection test for LinguaSub.",
                },
            ],
            "temperature": 0,
            "max_tokens": 12,
            "stream": False,
        }

    def _post_json(
        self,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        context_label: str,
        debug_context: TranslationRequestDebugContext | None = None,
    ) -> dict[str, Any]:
        if not api_key:
            raise ProviderApiError(
                f"Translation request is missing an API key while using {context_label}."
            )

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            url=url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Connection": "close",
            },
            method="POST",
        )

        max_attempts = 1 + NETWORK_RETRY_LIMIT
        for attempt_index in range(1, max_attempts + 1):
            try:
                with request.urlopen(http_request, timeout=timeout_seconds) as response:
                    response_text = response.read().decode("utf-8")
                break
            except error.HTTPError as exc:
                error_text = exc.read().decode("utf-8", errors="replace")
                raise ProviderApiError(
                    f"Translation request failed with HTTP {exc.code} while using "
                    f"{context_label}. {error_text}"
                    + _build_transport_error_suffix(
                        debug_context=debug_context,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        exc=exc,
                    )
                ) from exc
            except (
                socket.timeout,
                TimeoutError,
                ConnectionResetError,
                ConnectionAbortedError,
                BrokenPipeError,
                error.URLError,
            ) as exc:
                should_retry = (
                    attempt_index < max_attempts and _is_retryable_transport_error(exc)
                )
                if should_retry:
                    time.sleep(NETWORK_RETRY_BACKOFF_SECONDS * attempt_index)
                    continue

                if _is_timeout_transport_error(exc):
                    raise ProviderTimeoutError(
                        f"Translation request timed out after {timeout_seconds}s while using "
                        f"{context_label}."
                        + _build_transport_error_suffix(
                            debug_context=debug_context,
                            attempt_index=attempt_index,
                            max_attempts=max_attempts,
                            exc=exc,
                        )
                    ) from exc

                raise ProviderApiError(
                    f"Translation request hit a network error while using {context_label}."
                    + _build_transport_error_suffix(
                        debug_context=debug_context,
                        attempt_index=attempt_index,
                        max_attempts=max_attempts,
                        exc=exc,
                    )
                ) from exc

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise TranslationParseError(
                f"{self.provider_name} returned invalid JSON."
            ) from exc

    def _extract_message_content(self, response_data: dict[str, Any]) -> str:
        try:
            message = response_data["choices"][0]["message"]
            content = message.get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationParseError("Provider response is missing message content.") from exc

        if not isinstance(content, str) or not content.strip():
            raise TranslationParseError("Provider returned empty translation content.")

        return content

    def _parse_translation_json(
        self,
        content: str,
        *,
        prepared_content: PreparedTranslationJsonContent | None = None,
    ) -> ParsedTranslationContent:
        normalized_content = (
            prepared_content.normalizedContent
            if prepared_content is not None
            else _prepare_translation_json_content(content).normalizedContent
        )
        try:
            payload = json.loads(normalized_content)
        except json.JSONDecodeError as exc:
            raise TranslationParseError("Translation content is not valid JSON.") from exc

        translations = payload.get("translations")
        if not isinstance(translations, list):
            raise TranslationParseError("Translation JSON is missing 'translations'.")

        translated_by_id: dict[str, str] = {}
        returned_ids: list[str] = []
        empty_text_ids: list[str] = []
        invalid_items: list[str] = []
        for item in translations:
            if not isinstance(item, dict):
                invalid_items.append("non-dict item")
                continue

            segment_id = item.get("id")
            translated_text = item.get("translatedText")
            if isinstance(segment_id, str):
                returned_ids.append(segment_id)
            else:
                invalid_items.append("item with missing or invalid id")
                continue

            if not isinstance(translated_text, str):
                invalid_items.append(f"id={segment_id}: missing or invalid translatedText")
                continue

            translated_by_id[segment_id] = translated_text
            if not translated_text.strip():
                empty_text_ids.append(segment_id)

        deduped_returned_ids = list(dict.fromkeys(returned_ids))
        deduped_empty_text_ids = list(dict.fromkeys(empty_text_ids))
        deduped_invalid_items = list(dict.fromkeys(invalid_items))

        return ParsedTranslationContent(
            translatedById=translated_by_id,
            returnedIds=deduped_returned_ids,
            emptyTextIds=deduped_empty_text_ids,
            invalidItems=deduped_invalid_items,
        )


class OpenAICompatibleAdapter(ChatCompletionTranslationAdapter):
    def __init__(self) -> None:
        super().__init__("openaiCompatible")


class DeepSeekAdapter(ChatCompletionTranslationAdapter):
    def __init__(self) -> None:
        super().__init__("deepseek")


ADAPTERS: dict[ProviderName, TranslationProviderAdapter] = {
    "openaiCompatible": OpenAICompatibleAdapter(),
    "deepseek": DeepSeekAdapter(),
}


def chunk_segments(
    segments: list[SubtitleSegment],
    batch_size: int = DEFAULT_BATCH_SIZE,
    char_limit: int = DEFAULT_CHAR_LIMIT,
) -> list[list[SubtitleSegment]]:
    batches: list[list[SubtitleSegment]] = []
    current_batch: list[SubtitleSegment] = []
    current_chars = 0

    for segment in segments:
        segment_chars = len(segment.sourceText)
        exceeds_batch_size = len(current_batch) >= batch_size
        exceeds_char_limit = current_batch and (current_chars + segment_chars > char_limit)

        if exceeds_batch_size or exceeds_char_limit:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append(segment)
        current_chars += segment_chars

    if current_batch:
        batches.append(current_batch)

    return batches


def translate_segments(
    segments: list[SubtitleSegment],
    config: AppConfig,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> TranslationBatchResult:
    resolved_provider_config = resolve_translation_provider_config(config)

    if not segments:
        return TranslationBatchResult(
            segments=[],
            provider=resolved_provider_config.provider,
            model=resolved_provider_config.model,
            baseUrl=resolved_provider_config.baseUrl,
        )

    _validate_segments_for_translation(segments)

    adapter = ADAPTERS.get(resolved_provider_config.provider)
    if adapter is None:
        raise ProviderApiError(
            f"Unsupported translation provider '{resolved_provider_config.provider}'."
        )

    translated_segments: list[SubtitleSegment] = []
    for batch in chunk_segments(segments, batch_size=batch_size):
        translated_segments.extend(
            adapter.translate_batch(
                segments=batch,
                config=config,
                timeout_seconds=timeout_seconds,
            )
        )

    return TranslationBatchResult(
        segments=translated_segments,
        provider=resolved_provider_config.provider,
        model=resolved_provider_config.model,
        baseUrl=resolved_provider_config.baseUrl,
    )


def validate_translation_config(
    config: AppConfig,
    timeout_seconds: int = 20,
) -> TranslationConfigValidationResult:
    resolved_provider_config = resolve_translation_provider_config(config)
    adapter = ADAPTERS.get(resolved_provider_config.provider)
    if adapter is None:
        raise ProviderApiError(
            f"Unsupported translation provider '{resolved_provider_config.provider}'."
        )

    return adapter.validate_connection(
        config=config,
        timeout_seconds=timeout_seconds,
    )


# CamelCase alias keeps the main entry name aligned with the requirement text.
def translateSegments(
    segments: list[SubtitleSegment],
    config: AppConfig,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> TranslationBatchResult:
    return translate_segments(
        segments=segments,
        config=config,
        timeout_seconds=timeout_seconds,
        batch_size=batch_size,
    )


validateTranslationConfig = validate_translation_config
