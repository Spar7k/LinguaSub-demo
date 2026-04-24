"""Minimal sequential subtitle/audio alignment for imported English subtitles."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

from .models import JsonModel, SubtitleSegment

MAX_REFERENCE_WINDOW = 3
STRONG_SINGLE_MATCH_SCORE = 0.93
MIN_ACCEPTABLE_MATCH_SCORE = 0.74
MIN_TOKEN_RECALL = 0.55

SPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(r"[^\w\s]")


class SubtitleAlignmentServiceError(ValueError):
    """Raised when imported subtitles cannot be aligned safely enough."""


@dataclass(slots=True)
class SubtitleAlignmentDiagnostics(JsonModel):
    status: Literal["scaffold"] = "scaffold"
    inputCueCount: int = 0
    referenceSegmentCount: int = 0
    matchedCueCount: int = 0
    fallbackCueCount: int = 0
    matchedWithSingleAsrCount: int = 0
    matchedWithMultiAsrCount: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SubtitleAlignmentResult(JsonModel):
    segments: list[SubtitleSegment] = field(default_factory=list)
    diagnostics: SubtitleAlignmentDiagnostics = field(
        default_factory=SubtitleAlignmentDiagnostics
    )


@dataclass(slots=True)
class AlignmentCandidate:
    startIndex: int
    endIndex: int
    windowSize: int
    normalizedText: str
    score: float
    tokenRecall: float


def _normalize_text(text: str) -> str:
    lowered = text.casefold().replace("\n", " ").replace("\r", " ")
    without_punctuation = PUNCTUATION_RE.sub(" ", lowered)
    return SPACE_RE.sub(" ", without_punctuation).strip()


def _tokenize(normalized_text: str) -> list[str]:
    if not normalized_text:
        return []
    return [token for token in normalized_text.split(" ") if token]


def _token_recall(source_tokens: list[str], candidate_tokens: list[str]) -> float:
    if not source_tokens or not candidate_tokens:
        return 0.0

    candidate_counts = Counter(candidate_tokens)
    matched = 0
    for token in source_tokens:
        if candidate_counts[token] > 0:
            matched += 1
            candidate_counts[token] -= 1
    return matched / len(source_tokens)


def _length_similarity(source_text: str, candidate_text: str) -> float:
    if not source_text or not candidate_text:
        return 0.0

    source_length = len(source_text)
    candidate_length = len(candidate_text)
    return min(source_length, candidate_length) / max(source_length, candidate_length)


def _score_candidate(source_text: str, candidate_text: str) -> tuple[float, float]:
    normalized_source = _normalize_text(source_text)
    normalized_candidate = _normalize_text(candidate_text)
    if not normalized_source or not normalized_candidate:
        return 0.0, 0.0

    source_tokens = _tokenize(normalized_source)
    candidate_tokens = _tokenize(normalized_candidate)
    sequence_score = SequenceMatcher(
        None,
        normalized_source,
        normalized_candidate,
    ).ratio()
    token_recall = _token_recall(source_tokens, candidate_tokens)
    length_score = _length_similarity(normalized_source, normalized_candidate)
    score = (sequence_score * 0.6) + (token_recall * 0.3) + (length_score * 0.1)
    return score, token_recall


def _join_reference_window(reference_segments: list[SubtitleSegment]) -> str:
    return " ".join(
        segment.sourceText.strip()
        for segment in reference_segments
        if segment.sourceText.strip()
    ).strip()


def _build_candidate(
    *,
    reference_segments: list[SubtitleSegment],
    start_index: int,
    window_size: int,
    subtitle_segment: SubtitleSegment,
) -> AlignmentCandidate | None:
    window = reference_segments[start_index : start_index + window_size]
    if len(window) != window_size:
        return None

    candidate_text = _join_reference_window(window)
    normalized_candidate_text = _normalize_text(candidate_text)
    if not normalized_candidate_text:
        return None

    score, token_recall = _score_candidate(
        subtitle_segment.sourceText,
        candidate_text,
    )
    return AlignmentCandidate(
        startIndex=start_index,
        endIndex=start_index + window_size - 1,
        windowSize=window_size,
        normalizedText=normalized_candidate_text,
        score=score,
        tokenRecall=token_recall,
    )


def _is_acceptable_match(candidate: AlignmentCandidate) -> bool:
    return (
        candidate.score >= MIN_ACCEPTABLE_MATCH_SCORE
        and candidate.tokenRecall >= MIN_TOKEN_RECALL
    )


def _select_best_candidate(
    *,
    subtitle_segment: SubtitleSegment,
    reference_segments: list[SubtitleSegment],
    start_index: int,
) -> AlignmentCandidate | None:
    single_candidate = _build_candidate(
        reference_segments=reference_segments,
        start_index=start_index,
        window_size=1,
        subtitle_segment=subtitle_segment,
    )
    if (
        single_candidate
        and _is_acceptable_match(single_candidate)
        and single_candidate.score >= STRONG_SINGLE_MATCH_SCORE
    ):
        return single_candidate

    candidates: list[AlignmentCandidate] = []
    for window_size in range(1, MAX_REFERENCE_WINDOW + 1):
        candidate = _build_candidate(
            reference_segments=reference_segments,
            start_index=start_index,
            window_size=window_size,
            subtitle_segment=subtitle_segment,
        )
        if candidate and _is_acceptable_match(candidate):
            candidates.append(candidate)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: (item.score, item.tokenRecall, -item.windowSize),
    )


def _build_aligned_segment(
    *,
    subtitle_segment: SubtitleSegment,
    reference_segments: list[SubtitleSegment],
    candidate: AlignmentCandidate,
) -> SubtitleSegment:
    window = reference_segments[candidate.startIndex : candidate.endIndex + 1]
    return SubtitleSegment(
        id=subtitle_segment.id,
        start=window[0].start,
        end=window[-1].end,
        sourceText=subtitle_segment.sourceText,
        translatedText="",
        sourceLanguage=subtitle_segment.sourceLanguage,
        targetLanguage=subtitle_segment.targetLanguage,
    )


def _build_fallback_segment(subtitle_segment: SubtitleSegment) -> SubtitleSegment:
    return SubtitleSegment(
        id=subtitle_segment.id,
        start=subtitle_segment.start,
        end=subtitle_segment.end,
        sourceText=subtitle_segment.sourceText,
        translatedText="",
        sourceLanguage=subtitle_segment.sourceLanguage,
        targetLanguage=subtitle_segment.targetLanguage,
    )


def align_external_subtitles_to_reference(
    *,
    subtitle_segments: list[SubtitleSegment],
    reference_segments: list[SubtitleSegment],
) -> SubtitleAlignmentResult:
    if not subtitle_segments:
        raise SubtitleAlignmentServiceError("英文 SRT 中没有可用于对齐的字幕段。")

    if not reference_segments:
        raise SubtitleAlignmentServiceError(
            "英语语音识别结果为空，暂时无法参考语音时间轴进行重对齐。"
        )

    aligned_segments: list[SubtitleSegment] = []
    matched_count = 0
    fallback_count = 0
    matched_with_single_count = 0
    matched_with_multi_count = 0
    reference_index = 0

    for subtitle_segment in subtitle_segments:
        if reference_index < len(reference_segments):
            candidate = _select_best_candidate(
                subtitle_segment=subtitle_segment,
                reference_segments=reference_segments,
                start_index=reference_index,
            )
        else:
            candidate = None

        if candidate is None:
            aligned_segments.append(_build_fallback_segment(subtitle_segment))
            fallback_count += 1
            continue

        aligned_segments.append(
            _build_aligned_segment(
                subtitle_segment=subtitle_segment,
                reference_segments=reference_segments,
                candidate=candidate,
            )
        )
        matched_count += 1
        if candidate.windowSize == 1:
            matched_with_single_count += 1
        else:
            matched_with_multi_count += 1
        reference_index = candidate.endIndex + 1

    notes = [
        "当前为最小可用重对齐：按顺序比较英文 SRT 文本与英语 ASR 片段，并优先使用更贴近语音的时间轴。"
    ]
    if fallback_count > 0:
        notes.append("未能稳定匹配的字幕段会保留原始 SRT 时间轴，不会强行套用错误时间。")

    diagnostics = SubtitleAlignmentDiagnostics(
        status="scaffold",
        inputCueCount=len(subtitle_segments),
        referenceSegmentCount=len(reference_segments),
        matchedCueCount=matched_count,
        fallbackCueCount=fallback_count,
        matchedWithSingleAsrCount=matched_with_single_count,
        matchedWithMultiAsrCount=matched_with_multi_count,
        notes=notes,
    )
    return SubtitleAlignmentResult(
        segments=aligned_segments,
        diagnostics=diagnostics,
    )


def alignExternalSubtitlesToReference(
    *,
    subtitle_segments: list[SubtitleSegment],
    reference_segments: list[SubtitleSegment],
) -> SubtitleAlignmentResult:
    return align_external_subtitles_to_reference(
        subtitle_segments=subtitle_segments,
        reference_segments=reference_segments,
    )
