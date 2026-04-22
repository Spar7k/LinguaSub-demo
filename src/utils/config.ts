import type {
  ApiProviderConfig,
  AppConfig,
  OutputMode,
  ProviderName,
  TranscriptionProviderName,
} from '../types/models'

function safeText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function safeTrim(value: unknown): string {
  return safeText(value).trim()
}

export function getProviderModel(config: AppConfig, providerName: ProviderName) {
  const providers = Array.isArray(config.apiProviders) ? config.apiProviders : []
  return providers.find((provider) => provider.provider === providerName) ?? null
}

export function selectProvider(config: AppConfig, providerName: ProviderName): AppConfig {
  const activeProvider = getProviderModel(config, providerName)

  return {
    ...config,
    defaultProvider: providerName,
    apiKey: activeProvider?.apiKey ?? '',
    baseUrl: activeProvider?.baseUrl ?? config.baseUrl,
    model: activeProvider?.model ?? config.model,
  }
}

export function updateActiveProviderModel(config: AppConfig, model: string): AppConfig {
  return updateActiveProviderConfig(config, { model })
}

export function updateActiveProviderConfig(
  config: AppConfig,
  patch: Partial<Pick<ApiProviderConfig, 'apiKey' | 'baseUrl' | 'model'>>,
): AppConfig {
  return {
    ...config,
    apiKey: safeText(patch.apiKey ?? config.apiKey),
    baseUrl: safeText(patch.baseUrl ?? config.baseUrl),
    model: safeText(patch.model ?? config.model),
    apiProviders: (Array.isArray(config.apiProviders) ? config.apiProviders : []).map((provider) =>
      provider.provider === config.defaultProvider ? { ...provider, ...patch } : provider,
    ),
  }
}

export function updateOutputMode(config: AppConfig, outputMode: OutputMode): AppConfig {
  return {
    ...config,
    outputMode,
  }
}

export function updateDefaultTranscriptionProvider(
  config: AppConfig,
  provider: TranscriptionProviderName,
): AppConfig {
  return {
    ...config,
    defaultTranscriptionProvider: provider,
    speechProvider: provider,
  }
}

export function updateSpeechConfig(
  config: AppConfig,
  patch: Partial<
    Pick<
      AppConfig,
      | 'speechApiKey'
      | 'speechBaseUrl'
      | 'speechModel'
      | 'baiduAppId'
      | 'baiduApiKey'
      | 'baiduDevPid'
      | 'baiduCuid'
      | 'baiduFileAppId'
      | 'baiduFileApiKey'
      | 'baiduFileSecretKey'
      | 'baiduFileDevPid'
      | 'tencentAppId'
      | 'tencentSecretId'
      | 'tencentSecretKey'
      | 'tencentEngineModelType'
      | 'tencentFileSecretId'
      | 'tencentFileSecretKey'
      | 'tencentFileEngineModelType'
      | 'xfyunAppId'
      | 'xfyunSecretKey'
      | 'xfyunSpeedAppId'
      | 'xfyunSpeedApiKey'
      | 'xfyunSpeedApiSecret'
    >
  >,
): AppConfig {
  return {
    ...config,
    speechApiKey: safeText(patch.speechApiKey ?? config.speechApiKey),
    speechBaseUrl: safeText(patch.speechBaseUrl ?? config.speechBaseUrl),
    speechModel: safeText(patch.speechModel ?? config.speechModel),
    baiduAppId: safeText(patch.baiduAppId ?? config.baiduAppId),
    baiduApiKey: safeText(patch.baiduApiKey ?? config.baiduApiKey),
    baiduDevPid: safeText(patch.baiduDevPid ?? config.baiduDevPid),
    baiduCuid: safeText(patch.baiduCuid ?? config.baiduCuid),
    baiduFileAppId: safeText(patch.baiduFileAppId ?? config.baiduFileAppId),
    baiduFileApiKey: safeText(patch.baiduFileApiKey ?? config.baiduFileApiKey),
    baiduFileSecretKey: safeText(patch.baiduFileSecretKey ?? config.baiduFileSecretKey),
    baiduFileDevPid: safeText(patch.baiduFileDevPid ?? config.baiduFileDevPid),
    tencentAppId: safeText(patch.tencentAppId ?? config.tencentAppId),
    tencentSecretId: safeText(patch.tencentSecretId ?? config.tencentSecretId),
    tencentSecretKey: safeText(patch.tencentSecretKey ?? config.tencentSecretKey),
    tencentEngineModelType: safeText(
      patch.tencentEngineModelType ?? config.tencentEngineModelType,
    ),
    tencentFileSecretId: safeText(patch.tencentFileSecretId ?? config.tencentFileSecretId),
    tencentFileSecretKey: safeText(patch.tencentFileSecretKey ?? config.tencentFileSecretKey),
    tencentFileEngineModelType: safeText(
      patch.tencentFileEngineModelType ?? config.tencentFileEngineModelType,
    ),
    xfyunAppId: safeText(patch.xfyunAppId ?? config.xfyunAppId),
    xfyunSecretKey: safeText(patch.xfyunSecretKey ?? config.xfyunSecretKey),
    xfyunSpeedAppId: safeText(patch.xfyunSpeedAppId ?? config.xfyunSpeedAppId),
    xfyunSpeedApiKey: safeText(patch.xfyunSpeedApiKey ?? config.xfyunSpeedApiKey),
    xfyunSpeedApiSecret: safeText(
      patch.xfyunSpeedApiSecret ?? config.xfyunSpeedApiSecret,
    ),
  }
}

export function isLocalSpeechProvider(provider: TranscriptionProviderName): boolean {
  return provider === 'localFasterWhisper'
}

export function isCloudSpeechProvider(provider: TranscriptionProviderName): boolean {
  return !isLocalSpeechProvider(provider)
}

export function hasConfiguredApiKey(config: AppConfig | null): boolean {
  return Boolean(safeTrim(config?.apiKey))
}

export function hasUsableTranslationConfig(config: AppConfig | null): config is AppConfig {
  if (!config) {
    return false
  }

  return Boolean(
    safeTrim(config.apiKey) &&
      safeTrim(config.baseUrl) &&
      safeTrim(config.model),
  )
}

export function hasUsableSpeechConfig(config: AppConfig | null): config is AppConfig {
  if (!config) {
    return false
  }

  switch (config.defaultTranscriptionProvider) {
    case 'baidu_realtime':
      return Boolean(
        safeTrim(config.baiduAppId) &&
          safeTrim(config.baiduApiKey) &&
          safeTrim(config.baiduDevPid) &&
          safeTrim(config.baiduCuid),
      )
    case 'tencent_realtime':
      return Boolean(
        safeTrim(config.tencentAppId) &&
          safeTrim(config.tencentSecretId) &&
          safeTrim(config.tencentSecretKey) &&
          safeTrim(config.tencentEngineModelType),
      )
    case 'baidu_file_async':
      return Boolean(
        safeTrim(config.baiduFileAppId) &&
          safeTrim(config.baiduFileApiKey) &&
          safeTrim(config.baiduFileSecretKey),
      )
    case 'tencent_file_async':
      return Boolean(
        safeTrim(config.tencentFileSecretId) &&
          safeTrim(config.tencentFileSecretKey) &&
          safeTrim(config.tencentFileEngineModelType),
      )
    case 'xfyun_lfasr':
      return Boolean(
        safeTrim(config.xfyunAppId) &&
          safeTrim(config.xfyunSecretKey),
      )
    case 'xfyun_speed_transcription':
      return Boolean(
        safeTrim(config.xfyunSpeedAppId) &&
          safeTrim(config.xfyunSpeedApiKey) &&
          safeTrim(config.xfyunSpeedApiSecret),
      )
    case 'openaiSpeech':
      return Boolean(
        safeTrim(config.speechApiKey) &&
          safeTrim(config.speechBaseUrl) &&
          safeTrim(config.speechModel),
      )
    case 'localFasterWhisper':
      return true
    default:
      return false
  }
}
