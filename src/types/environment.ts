import type { AsrModelSize, TranscriptionProviderName } from './models'

export type DependencyStatus = {
  key: 'backend' | 'ffmpeg' | 'fasterWhisperRuntime' | string
  label: string
  available: boolean
  requiredFor: string
  detectedPath: string | null
  installHint: string
  details: string
}

export type SpeechModelStatus = {
  size: AsrModelSize
  label: string
  available: boolean
  status: 'ready' | 'missing' | 'downloading' | 'error' | 'unavailable'
  detectedPath: string | null
  statusText: string
  details: string
  actionHint: string
}

export type SpeechModelDownloadStatus = {
  active: boolean
  modelSize: AsrModelSize | null
  status: 'idle' | 'starting' | 'downloading' | 'done' | 'error'
  targetPath: string | null
  usingDefaultStorage: boolean
  progress: number
  message: string
  error: string | null
}

export type SpeechModelCleanupResult = {
  removedModelPaths: string[]
  removedRootPaths: string[]
  removedMetadataPaths: string[]
  skippedPaths: string[]
  protectedPaths: string[]
  message: string
}

export type StartupCheckReport = {
  mode: 'development' | 'release'
  backendReachable: boolean
  pythonExecutable: string
  currentConfigPath: string
  recommendedConfigPath: string
  userDataDir: string
  defaultSpeechModelStorageDir: string
  speechModelStorageDir: string
  defaultProvider: string
  defaultTranscriptionProvider: TranscriptionProviderName
  defaultModel: string
  speechBaseUrl: string
  speechModel: string
  defaultAsrModelSize: AsrModelSize
  outputMode: string
  apiKeyConfigured: boolean
  speechApiConfigured: boolean
  readyForSrtWorkflow: boolean
  readyForMediaWorkflow: boolean
  readyForCloudTranscription: boolean
  readyForLocalTranscription: boolean
  exportRule: string
  dependencies: DependencyStatus[]
  speechModels: SpeechModelStatus[]
  activeModelDownload: SpeechModelDownloadStatus
  warnings: string[]
  actions: string[]
}
