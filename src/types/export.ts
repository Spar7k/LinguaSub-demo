import type { ContentSummaryResult } from './agent'

export type ExportFormat =
  | 'srt'
  | 'word'
  | 'recognition_text'
  | 'content_summary_word'

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
