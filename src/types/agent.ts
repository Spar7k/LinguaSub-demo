import type { AppConfig } from './models'

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
