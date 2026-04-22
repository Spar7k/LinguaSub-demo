import type { ApiProviderConfig, AppConfig } from '../types/models'
import { createDefaultAppConfig } from '../types/models'
import { getBackendUrl, requestJson } from './backendClient'

export type ApiProviderConfigPatch = Partial<ApiProviderConfig> &
  Pick<ApiProviderConfig, 'provider'>

export type AppConfigPatch = Partial<Omit<AppConfig, 'apiProviders'>> & {
  apiProviders?: ApiProviderConfigPatch[]
}

export type ValidateConfigResponse = {
  ok: boolean
  provider: AppConfig['defaultProvider']
  model: string
  baseUrl: string
  message: string
}

export type ValidateSpeechConfigResponse = {
  ok: boolean
  provider: AppConfig['defaultTranscriptionProvider']
  model: string
  baseUrl: string
  message: string
}

const SPEECH_VALIDATE_LOCAL_PATH = '/config/validate-speech'

function buildSpeechValidateLocalUrl(): string {
  return `${getBackendUrl()}${SPEECH_VALIDATE_LOCAL_PATH}`
}

function safeText(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function normalizeProviderConfig(
  value: unknown,
  fallbackProvider: ApiProviderConfig,
): ApiProviderConfig {
  if (!value || typeof value !== 'object') {
    return { ...fallbackProvider }
  }

  const rawProvider = value as Partial<ApiProviderConfig>
  return {
    provider: rawProvider.provider === fallbackProvider.provider
      ? rawProvider.provider
      : fallbackProvider.provider,
    displayName: safeText(rawProvider.displayName, fallbackProvider.displayName),
    apiKey: safeText(rawProvider.apiKey),
    baseUrl: safeText(rawProvider.baseUrl, fallbackProvider.baseUrl),
    model: safeText(rawProvider.model, fallbackProvider.model),
    enabled: typeof rawProvider.enabled === 'boolean' ? rawProvider.enabled : fallbackProvider.enabled,
  }
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.filter((item): item is string => typeof item === 'string')
}

function normalizeAppConfig(value: unknown): AppConfig {
  const defaults = createDefaultAppConfig()
  if (!value || typeof value !== 'object') {
    return defaults
  }

  const rawConfig = value as Partial<AppConfig>
  const providerDefaults = defaults.apiProviders
  const mergedProviders = providerDefaults.map((providerDefault) => {
    const rawProvider = Array.isArray(rawConfig.apiProviders)
      ? rawConfig.apiProviders.find((provider) => provider?.provider === providerDefault.provider)
      : null
    return normalizeProviderConfig(rawProvider, providerDefault)
  })

  return {
    ...defaults,
    apiProviders: mergedProviders,
    defaultProvider:
      rawConfig.defaultProvider === 'deepseek' || rawConfig.defaultProvider === 'openaiCompatible'
        ? rawConfig.defaultProvider
        : defaults.defaultProvider,
    defaultTranscriptionProvider:
      rawConfig.defaultTranscriptionProvider === 'localFasterWhisper' ||
      rawConfig.defaultTranscriptionProvider === 'openaiSpeech' ||
      rawConfig.defaultTranscriptionProvider === 'baidu_realtime' ||
      rawConfig.defaultTranscriptionProvider === 'baidu_file_async' ||
      rawConfig.defaultTranscriptionProvider === 'tencent_realtime' ||
      rawConfig.defaultTranscriptionProvider === 'tencent_file_async' ||
      rawConfig.defaultTranscriptionProvider === 'xfyun_lfasr' ||
      rawConfig.defaultTranscriptionProvider === 'xfyun_speed_transcription'
        ? rawConfig.defaultTranscriptionProvider
        : defaults.defaultTranscriptionProvider,
    speechProvider:
      rawConfig.speechProvider === 'localFasterWhisper' ||
      rawConfig.speechProvider === 'openaiSpeech' ||
      rawConfig.speechProvider === 'baidu_realtime' ||
      rawConfig.speechProvider === 'baidu_file_async' ||
      rawConfig.speechProvider === 'tencent_realtime' ||
      rawConfig.speechProvider === 'tencent_file_async' ||
      rawConfig.speechProvider === 'xfyun_lfasr' ||
      rawConfig.speechProvider === 'xfyun_speed_transcription'
        ? rawConfig.speechProvider
        : rawConfig.defaultTranscriptionProvider === 'localFasterWhisper' ||
            rawConfig.defaultTranscriptionProvider === 'openaiSpeech' ||
            rawConfig.defaultTranscriptionProvider === 'baidu_realtime' ||
            rawConfig.defaultTranscriptionProvider === 'baidu_file_async' ||
            rawConfig.defaultTranscriptionProvider === 'tencent_realtime' ||
            rawConfig.defaultTranscriptionProvider === 'tencent_file_async' ||
            rawConfig.defaultTranscriptionProvider === 'xfyun_lfasr' ||
            rawConfig.defaultTranscriptionProvider === 'xfyun_speed_transcription'
          ? rawConfig.defaultTranscriptionProvider
          : defaults.speechProvider,
    apiKey: safeText(rawConfig.apiKey),
    baseUrl: safeText(rawConfig.baseUrl, defaults.baseUrl),
    model: safeText(rawConfig.model, defaults.model),
    speechApiKey: safeText(rawConfig.speechApiKey),
    speechBaseUrl: safeText(rawConfig.speechBaseUrl, defaults.speechBaseUrl),
    speechModel: safeText(rawConfig.speechModel, defaults.speechModel),
    baiduAppId: safeText(rawConfig.baiduAppId),
    baiduApiKey: safeText(rawConfig.baiduApiKey),
    baiduDevPid: safeText(rawConfig.baiduDevPid, defaults.baiduDevPid),
    baiduCuid: safeText(rawConfig.baiduCuid, defaults.baiduCuid),
    baiduFileAppId: safeText(rawConfig.baiduFileAppId),
    baiduFileApiKey: safeText(rawConfig.baiduFileApiKey),
    baiduFileSecretKey: safeText(rawConfig.baiduFileSecretKey),
    baiduFileDevPid: safeText(rawConfig.baiduFileDevPid, defaults.baiduFileDevPid),
    tencentAppId: safeText(rawConfig.tencentAppId),
    tencentSecretId: safeText(rawConfig.tencentSecretId),
    tencentSecretKey: safeText(rawConfig.tencentSecretKey),
    tencentEngineModelType: safeText(
      rawConfig.tencentEngineModelType,
      defaults.tencentEngineModelType,
    ),
    tencentFileSecretId: safeText(rawConfig.tencentFileSecretId),
    tencentFileSecretKey: safeText(rawConfig.tencentFileSecretKey),
    tencentFileEngineModelType: safeText(
      rawConfig.tencentFileEngineModelType,
      defaults.tencentFileEngineModelType,
    ),
    xfyunAppId: safeText(rawConfig.xfyunAppId),
    xfyunSecretKey: safeText(rawConfig.xfyunSecretKey),
    xfyunSpeedAppId: safeText(rawConfig.xfyunSpeedAppId),
    xfyunSpeedApiKey: safeText(rawConfig.xfyunSpeedApiKey),
    xfyunSpeedApiSecret: safeText(rawConfig.xfyunSpeedApiSecret),
    uploadCosSecretId: safeText(rawConfig.uploadCosSecretId),
    uploadCosSecretKey: safeText(rawConfig.uploadCosSecretKey),
    uploadCosBucket: safeText(rawConfig.uploadCosBucket),
    uploadCosRegion: safeText(rawConfig.uploadCosRegion),
    outputMode:
      rawConfig.outputMode === 'single' || rawConfig.outputMode === 'bilingual'
        ? rawConfig.outputMode
        : defaults.outputMode,
    modelStoragePath: safeText(rawConfig.modelStoragePath),
    managedModelRoots: normalizeStringArray(rawConfig.managedModelRoots),
    managedModelPaths: normalizeStringArray(rawConfig.managedModelPaths),
  }
}

export async function loadConfig(): Promise<AppConfig> {
  const config = await requestJson<AppConfig>('/config')
  return normalizeAppConfig(config)
}

export async function saveConfig(config: AppConfig): Promise<AppConfig> {
  const saved = await requestJson<AppConfig>('/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  })
  return normalizeAppConfig(saved)
}

export async function updateConfig(patch: AppConfigPatch): Promise<AppConfig> {
  const updated = await requestJson<AppConfig>('/config', {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
  return normalizeAppConfig(updated)
}

export async function validateConfig(config: AppConfig): Promise<ValidateConfigResponse> {
  return requestJson<ValidateConfigResponse>('/config/validate', {
    method: 'POST',
    body: JSON.stringify({ config }),
  })
}

export async function validateSpeechConfig(
  config: AppConfig,
): Promise<ValidateSpeechConfigResponse> {
  const localUrl = buildSpeechValidateLocalUrl()
  const provider = config.speechProvider || config.defaultTranscriptionProvider
  const baseUrl =
    provider === 'baidu_realtime'
      ? 'wss://vop.baidu.com/realtime_asr'
      : provider === 'baidu_file_async'
        ? 'baidu://file-async'
      : provider === 'tencent_realtime'
        ? `wss://asr.cloud.tencent.com/asr/v2/${config.tencentAppId || '<appid>'}`
        : provider === 'tencent_file_async'
          ? 'tencent://file-async'
          : provider === 'xfyun_lfasr'
            ? 'xfyun://lfasr'
            : provider === 'xfyun_speed_transcription'
              ? 'xfyun://speed-transcription'
        : config.speechBaseUrl
  const model =
    provider === 'baidu_realtime'
      ? config.baiduDevPid
      : provider === 'baidu_file_async'
        ? config.baiduFileDevPid
      : provider === 'tencent_realtime'
        ? config.tencentEngineModelType
        : provider === 'tencent_file_async'
          ? config.tencentFileEngineModelType
          : provider === 'xfyun_lfasr'
            ? 'lfasr'
            : provider === 'xfyun_speed_transcription'
              ? 'speed-transcription'
        : config.speechModel
  console.info('[LinguaSub][Settings] speech validate:start', {
    localPath: SPEECH_VALIDATE_LOCAL_PATH,
    localUrl,
    provider,
    baseUrl,
    model,
  })

  try {
    return await requestJson<ValidateSpeechConfigResponse>(SPEECH_VALIDATE_LOCAL_PATH, {
      method: 'POST',
      body: JSON.stringify({ config }),
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : '识别连接测试失败。'
    console.error('[LinguaSub][Settings] speech validate:failed', {
      localPath: SPEECH_VALIDATE_LOCAL_PATH,
      localUrl,
      provider,
      baseUrl,
      model,
      error: message,
    })

    if (/route not found/i.test(message)) {
      throw new Error(
        `本地测试接口不存在：${SPEECH_VALIDATE_LOCAL_PATH}。请确认 LinguaSub 后端已更新到最新版本。`,
      )
    }

    throw new Error(message || '识别连接测试失败。')

    if (/route not found/i.test(message)) {
      throw new Error(
        `本地测试接口不存在：${SPEECH_VALIDATE_LOCAL_PATH}。请确认 LinguaSub 后端已更新到最新版本。`,
      )
    }

    throw error instanceof Error ? error : new Error(message)
  }
}
