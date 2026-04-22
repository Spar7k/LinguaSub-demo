// Step 2 standardizes all timeline values in milliseconds.
// Using integers avoids floating-point drift when exporting SRT files.

export type LanguageCode = 'auto' | 'zh-CN' | 'en' | 'ja' | 'ko'

export type ProviderName = 'openaiCompatible' | 'deepseek'

export type TranscriptionProviderName = string

export type OutputMode = 'bilingual' | 'single'

export type TranslationTaskStatus = 'queued' | 'translating' | 'done' | 'error'

export type ProjectStatus = 'idle' | 'transcribing' | 'translating' | 'exporting' | 'done' | 'error'

export type MediaType = 'video' | 'audio' | 'subtitle'

export type AsrModelSize = 'tiny' | 'base' | 'small'

export type ProjectFile = {
  path: string
  name: string
  mediaType: MediaType
  extension: string
  requiresAsr: boolean
}

export type SubtitleSegment = {
  id: string
  start: number
  end: number
  sourceText: string
  translatedText: string
  sourceLanguage: LanguageCode
  targetLanguage: LanguageCode
}

export type ApiProviderConfig = {
  provider: ProviderName
  displayName: string
  apiKey: string
  baseUrl: string
  model: string
  enabled: boolean
}

export type AppConfig = {
  apiProviders: ApiProviderConfig[]
  defaultProvider: ProviderName
  defaultTranscriptionProvider: TranscriptionProviderName
  speechProvider: TranscriptionProviderName
  // These three fields mirror the active provider so the settings form
  // can bind to one flat object without digging into nested arrays.
  apiKey: string
  baseUrl: string
  model: string
  speechApiKey: string
  speechBaseUrl: string
  speechModel: string
  baiduAppId: string
  baiduApiKey: string
  baiduDevPid: string
  baiduCuid: string
  baiduFileAppId: string
  baiduFileApiKey: string
  baiduFileSecretKey: string
  baiduFileDevPid: string
  tencentAppId: string
  tencentSecretId: string
  tencentSecretKey: string
  tencentEngineModelType: string
  tencentFileSecretId: string
  tencentFileSecretKey: string
  tencentFileEngineModelType: string
  xfyunAppId: string
  xfyunSecretKey: string
  xfyunSpeedAppId: string
  xfyunSpeedApiKey: string
  xfyunSpeedApiSecret: string
  uploadCosSecretId: string
  uploadCosSecretKey: string
  uploadCosBucket: string
  uploadCosRegion: string
  outputMode: OutputMode
  modelStoragePath: string
  managedModelRoots: string[]
  managedModelPaths: string[]
}

export type TranslationTask = {
  provider: ProviderName
  model: string
  sourceLanguage: LanguageCode
  targetLanguage: LanguageCode
  segments: SubtitleSegment[]
  status: TranslationTaskStatus
}

export type ProjectState = {
  currentFile: ProjectFile | null
  segments: SubtitleSegment[]
  status: ProjectStatus
  error: string | null
}

export function createDefaultAppConfig(): AppConfig {
  return {
    apiProviders: [
      {
        provider: 'openaiCompatible',
        displayName: 'OpenAI Compatible',
        apiKey: '',
        baseUrl: 'https://api.openai.com/v1',
        model: 'gpt-4.1-mini',
        enabled: true,
      },
      {
        provider: 'deepseek',
        displayName: 'DeepSeek',
        apiKey: '',
        baseUrl: 'https://api.deepseek.com/v1',
        model: 'deepseek-chat',
        enabled: true,
      },
    ],
    defaultProvider: 'openaiCompatible',
    defaultTranscriptionProvider: 'baidu_realtime',
    speechProvider: 'baidu_realtime',
    apiKey: '',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4.1-mini',
    speechApiKey: '',
    speechBaseUrl: 'https://api.openai.com/v1',
    speechModel: 'whisper-1',
    baiduAppId: '',
    baiduApiKey: '',
    baiduDevPid: '15372',
    baiduCuid: 'linguasub-desktop',
    baiduFileAppId: '',
    baiduFileApiKey: '',
    baiduFileSecretKey: '',
    baiduFileDevPid: '15372',
    tencentAppId: '',
    tencentSecretId: '',
    tencentSecretKey: '',
    tencentEngineModelType: '16k_zh',
    tencentFileSecretId: '',
    tencentFileSecretKey: '',
    tencentFileEngineModelType: '16k_zh',
    xfyunAppId: '',
    xfyunSecretKey: '',
    xfyunSpeedAppId: '',
    xfyunSpeedApiKey: '',
    xfyunSpeedApiSecret: '',
    uploadCosSecretId: '',
    uploadCosSecretKey: '',
    uploadCosBucket: '',
    uploadCosRegion: '',
    outputMode: 'bilingual',
    modelStoragePath: '',
    managedModelRoots: [],
    managedModelPaths: [],
  }
}

export function createEmptyProjectState(): ProjectState {
  return {
    currentFile: null,
    segments: [],
    status: 'idle',
    error: null,
  }
}
