import type {
  AppConfig,
  LanguageCode,
  OutputMode,
  ProviderName,
  ProjectFile,
  SubtitleSegment,
} from './models'
import type { TranscriptionDiagnostics } from './transcription'

export type VideoSubtitleSourceLanguage = 'zh' | 'en'

export type VideoSubtitlePipeline =
  | 'transcribeOnly'
  | 'transcribeAndTranslate'
  | 'alignAndTranslate'

export type VideoSubtitleDraft = {
  videoPath: string
  subtitlePath: string
  sourceLanguage: VideoSubtitleSourceLanguage
  outputMode: OutputMode
}

export type VideoSubtitleRunRequest = {
  videoPath: string
  subtitlePath?: string | null
  sourceLanguage: VideoSubtitleSourceLanguage
  outputMode: OutputMode
  config?: AppConfig | null
}

export type VideoSubtitleAlignmentDiagnostics = {
  status: 'scaffold'
  inputCueCount: number
  referenceSegmentCount: number
  matchedCueCount: number
  fallbackCueCount: number
  matchedWithSingleAsrCount: number
  matchedWithMultiAsrCount: number
  notes: string[]
} | null

export type VideoSubtitleRunDiagnostics = {
  transcription: TranscriptionDiagnostics
  translation: {
    provider: ProviderName
    model: string
    baseUrl: string
  } | null
  alignment: VideoSubtitleAlignmentDiagnostics
  notes: string[]
}

export type VideoSubtitleRunResponse = {
  currentFile: ProjectFile
  segments: SubtitleSegment[]
  count: number
  sourceLanguage: LanguageCode
  outputMode: OutputMode
  pipeline: VideoSubtitlePipeline
  status: 'done'
  diagnostics: VideoSubtitleRunDiagnostics
}
