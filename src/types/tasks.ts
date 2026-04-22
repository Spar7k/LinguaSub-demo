import type { ImportResult } from './import'
import type { ProjectState } from './models'

export type TaskMode = 'extractAndTranslate' | 'translateSubtitle'

export type TaskEngineType =
  | 'cloudTranscription'
  | 'localTranscription'
  | 'subtitleImport'

export type TaskStatus =
  | 'queued'
  | 'transcribing'
  | 'translating'
  | 'editing'
  | 'exporting'
  | 'done'
  | 'error'
  | 'cancelled'

export type TaskLogLevel = 'info' | 'warning' | 'error'

export type SubtitleSummary = {
  segmentCount: number
  translatedCount: number
}

export type TaskLogEntry = {
  logId: string
  timestamp: string
  level: TaskLogLevel
  message: string
  details: string | null
}

export type TaskHistoryRecord = {
  taskId: string
  sourceFilePath: string
  sourceFileName: string
  taskMode: TaskMode
  sourceLanguage: string
  targetLanguage: string
  outputFormats: string[]
  engineType: TaskEngineType
  status: TaskStatus
  createdAt: string
  updatedAt: string
  exportPaths: string[]
  errorMessage: string | null
  subtitleSummary: SubtitleSummary | null
  importSnapshot: ImportResult | null
  projectSnapshot: ProjectState | null
  logs: TaskLogEntry[]
  transcriptionProvider: string | null
  transcriptionModelSize: string | null
  transcriptionQualityPreset: string | null
  translationProvider: string | null
  translationModel: string | null
  outputMode: string | null
}

export type TaskHistoryResponse = {
  tasks: TaskHistoryRecord[]
  count: number
}
