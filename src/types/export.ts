import type { ContentSummaryResult } from './agent'

export type ExportFormat<IncludeCommandAgentWord extends boolean = false> =
  | 'srt'
  | 'word'
  | 'recognition_text'
  | 'content_summary_word'
  | (IncludeCommandAgentWord extends true ? 'command_agent_word' : never)

export type CommandAgentWordExportFormat = Extract<
  ExportFormat<true>,
  'command_agent_word'
>

export type WordExportMode = 'bilingualTable' | 'transcript'

export type ExportResult = {
  path: string
  directory: string
  fileName: string
  format: ExportFormat
  bilingual: boolean
  wordMode: WordExportMode | null
  count: number
  conflictResolved: boolean
  sanitizedFileName: boolean
  status: 'done'
}

export type ContentSummaryWordExportRequest = {
  summary: ContentSummaryResult
  sourceFilePath?: string | null
  fileName?: string | null
}

export type ContentSummaryWordExportResult = ExportResult & {
  format: 'content_summary_word'
}

export interface CommandAgentWordContextSummary {
  videoName?: string
  subtitleCount?: number
  translatedCount?: number
  translationCoverage?: number
  sourceLanguage?: string
  targetLanguage?: string
  bilingualMode?: string
}

export interface CommandAgentWordExportRequest {
  instruction: string
  result: {
    intent?: string
    title: string
    summary?: string
    content: string
    suggestedActions?: string[]
  }
  contextSummary?: CommandAgentWordContextSummary
  createdAt?: string
  sourceFilePath: string
  fileName?: string | null
}

export type CommandAgentWordExportResult = Omit<ExportResult, 'format'> & {
  format: CommandAgentWordExportFormat
}
