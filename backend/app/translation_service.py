"""Translation service with provider adapters."""

from __future__ import annotations

import json
import socket
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
        payload = self._build_payload(segments, provider_config.model)
        response_data = self._post_json(
            url=self._build_endpoint(provider_config.baseUrl),
            api_key=provider_config.apiKey,
            payload=payload,
            timeout_seconds=timeout_seconds,
            context_label=_build_translation_request_context(provider_config),
        )
        content = self._extract_message_content(response_data)
        parsed_content = self._parse_translation_json(content)
        translated_by_id = parsed_content.translatedById
        expected_ids = [segment.id for segment in segments]
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
        content_preview = _build_content_preview(content)

        translated_segments: list[SubtitleSegment] = []
        for segment in segments:
            translated_text = translated_by_id.get(segment.id)
            if not translated_text:
                raise TranslationParseError(
                    "翻译结果缺项或异常，无法完成当前批次。"
                    f" 当前缺失 segment.id='{segment.id}'。"
                    f" expected_ids={_summarize_values(expected_ids)}"
                    f" returned_ids={_summarize_values(returned_ids)}"
                    f" missing_ids={_summarize_values(missing_ids)}"
                    f" empty_text_ids={_summarize_values(empty_text_ids)}"
                    f" unexpected_ids={_summarize_values(unexpected_ids)}"
                    f" invalid_items={_summarize_values(parsed_content.invalidItems)}"
                    f" content_preview={content_preview!r}"
                )

            updated_segment = deepcopy(segment)
            updated_segment.translatedText = translated_text.strip()
            translated_segments.append(updated_segment)

        return translated_segments

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
            },
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise ProviderApiError(
                f"Translation request failed with HTTP {exc.code} while using "
                f"{context_label}. {error_text}"
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderTimeoutError(
                f"Translation request timed out after {timeout_seconds}s while using "
                f"{context_label}."
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, socket.timeout):
                raise ProviderTimeoutError(
                    f"Translation request timed out after {timeout_seconds}s while using "
                    f"{context_label}."
                ) from exc
            raise ProviderApiError(
                f"Translation request hit a network error while using {context_label}. "
                f"{exc.reason}"
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

    def _parse_translation_json(self, content: str) -> ParsedTranslationContent:
        try:
            payload = json.loads(content)
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
