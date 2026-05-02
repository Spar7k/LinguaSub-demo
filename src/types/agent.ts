import type { AppConfig, SubtitleSegment } from './models'

export type AgentIssueSeverity = 'info' | 'warning' | 'error'

export type AgentIssueType =
  | 'empty_translation'
  | 'missing_translation'
  | 'timing_error'
  | 'too_long'
  | 'bilingual_format_error'
  | 'terminology_inconsistent'
  | 'unnatural_translation'

export type SubtitleAgentSegment = {
  id: string
  start: number
  end: number
  sourceText: string
  translatedText?: string
  sourceLanguage?: string
  targetLanguage?: string
}

export type SubtitleAgentRequest = {
  segments: SubtitleAgentSegment[]
  config: AppConfig
  sourceLanguage?: string
  targetLanguage?: string
  bilingualMode?: string
  timeoutSeconds?: number
}

export type SubtitleQualityIssue = {
  segmentId: string
  severity: AgentIssueSeverity
  type: AgentIssueType
  message: string
  suggestion?: string
}

export type SubtitleQualityResult = {
  score: number
  summary: string
  issues: SubtitleQualityIssue[]
  diagnostics?: Record<string, unknown>
}

export type ContentSummaryChapter = {
  start: number
  end: number
  title: string
  summary: string
}

export type ContentSummaryKeyword = {
  term: string
  translation?: string
  explanation?: string
}

export type ContentSummaryResult = {
  oneSentenceSummary: string
  chapters: ContentSummaryChapter[]
  keywords: ContentSummaryKeyword[]
  studyNotes: string
  diagnostics?: Record<string, unknown>
}

export type AgentStoredResult<T> = {
  result: T
  segmentSignature: string
  generatedAt: string
  segmentCount: number
}

export type AgentSessionState = {
  subtitleQuality: AgentStoredResult<SubtitleQualityResult> | null
  contentSummary: AgentStoredResult<ContentSummaryResult> | null
}

type SegmentSignatureInput = Pick<
  SubtitleSegment,
  'id' | 'start' | 'end' | 'sourceText' | 'translatedText'
>

function appendHashValue(hash: number, value: string): number {
  const normalizedValue = `${value.length}:${value};`
  let nextHash = hash

  for (let index = 0; index < normalizedValue.length; index += 1) {
    nextHash ^= normalizedValue.charCodeAt(index)
    nextHash = Math.imul(nextHash, 0x01000193) >>> 0
  }

  return nextHash
}

export function buildAgentSegmentSignature(
  segments: SegmentSignatureInput[],
): string {
  let hash = 0x811c9dc5

  hash = appendHashValue(hash, 'linguasub-agent-segments-v1')
  hash = appendHashValue(hash, String(segments.length))

  for (const segment of segments) {
    hash = appendHashValue(hash, segment.id)
    hash = appendHashValue(hash, String(segment.start))
    hash = appendHashValue(hash, String(segment.end))
    hash = appendHashValue(hash, segment.sourceText)
    hash = appendHashValue(hash, segment.translatedText)
  }

  return `v1:${segments.length}:${hash.toString(36)}`
}
