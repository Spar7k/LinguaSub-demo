export type ExportFormat = 'srt' | 'word'

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
