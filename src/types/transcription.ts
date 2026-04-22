import type {
  LanguageCode,
  SubtitleSegment,
  TranscriptionProviderName,
} from './models'

export type AsrInputLanguage = 'auto' | 'zh' | 'en' | 'ja' | 'ko'

export type AsrQualityPreset = 'speed' | 'balanced' | 'accuracy'

export type TranscriptionMode = 'cloud' | 'local'

export type TranscriptionDiagnostics = {
  provider: TranscriptionProviderName
  mode: TranscriptionMode
  model: string
  providerBaseUrl: string | null
  qualityPreset: string
  requestedLanguage: AsrInputLanguage
  detectedLanguage: LanguageCode
  preprocessingProfile: string
  rawSegmentCount: number
  finalSegmentCount: number
  readabilityPasses: string[]
  notes: string[]
}

export type TranscribeMediaResponse = {
  segments: SubtitleSegment[]
  count: number
  sourceLanguage: LanguageCode
  provider: TranscriptionProviderName
  mode: TranscriptionMode
  model: string
  baseUrl: string | null
  qualityPreset: string
  diagnostics: TranscriptionDiagnostics
  status: 'done'
}
