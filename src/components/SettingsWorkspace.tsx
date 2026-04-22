import { useEffect, useMemo, useState } from 'react'

import { SectionCard } from './SectionCard'
import {
  createDefaultAppConfig,
  type AppConfig,
  type OutputMode,
  type ProviderName,
  type TranscriptionProviderName,
} from '../types/models'
import {
  hasUsableSpeechConfig,
  hasUsableTranslationConfig,
  isLocalSpeechProvider,
  safeTrim,
  selectProvider,
  updateActiveProviderConfig,
  updateDefaultTranscriptionProvider,
  updateOutputMode,
  updateSpeechConfig,
} from '../utils/config'

type SettingsWorkspaceProps = {
  config: AppConfig | null
  configError: string | null
  isConfigLoading: boolean
  managedModelRoots: string[]
  currentLanguageLabel: string
  isUninstalling: boolean
  uninstallError: string | null
  onSaveConfig: (nextConfig: AppConfig) => Promise<void>
  onValidateConfig: (nextConfig: AppConfig) => Promise<string>
  onValidateSpeechConfig: (nextConfig: AppConfig) => Promise<string>
  onOpenImport: () => void
  onReloadConfig: () => void
  onStartUninstall: () => Promise<void>
}

type AsyncStatus = 'idle' | 'testing' | 'success' | 'error'
type AsyncFeedback = {
  status: AsyncStatus
  message: string
}

const PROVIDER_LABELS: Record<ProviderName, string> = {
  openaiCompatible: 'OpenAI 兼容接口',
  deepseek: 'DeepSeek',
}

const TRANSCRIPTION_PROVIDER_LABELS: Record<string, string> = {
  baidu_realtime: '百度实时识别（现有）',
  baidu_file_async: '百度音频文件转写',
  tencent_realtime: '腾讯实时识别（现有）',
  tencent_file_async: '腾讯录音文件识别',
  xfyun_lfasr: '讯飞长音频转写',
  openaiSpeech: 'OpenAI 兼容识别',
  localFasterWhisper: '本地识别（进阶 / 离线）',
  xfyun_speed_transcription: '讯飞极速录音转写大模型',
}

const TRANSCRIPTION_PROVIDER_OPTIONS: TranscriptionProviderName[] = [
  'baidu_realtime',
  'baidu_file_async',
  'tencent_realtime',
  'tencent_file_async',
  'xfyun_lfasr',
  'xfyun_speed_transcription',
  'openaiSpeech',
  'localFasterWhisper',
]

const FILE_ASYNC_SPEECH_PROVIDERS = new Set<TranscriptionProviderName>([
  'baidu_file_async',
  'tencent_file_async',
  'xfyun_lfasr',
  'xfyun_speed_transcription',
])

TRANSCRIPTION_PROVIDER_LABELS.xfyun_lfasr = '讯飞经典长音频转写'
TRANSCRIPTION_PROVIDER_LABELS.xfyun_speed_transcription = '讯飞极速录音转写大模型'

const OUTPUT_MODE_LABELS: Record<OutputMode, string> = {
  bilingual: '双语字幕',
  single: '单语字幕',
}

function createIdleFeedback(): AsyncFeedback {
  return { status: 'idle', message: '' }
}

function getStatusClassName(status: AsyncStatus, configured: boolean): string {
  if (status === 'success' || (status === 'idle' && configured)) {
    return 'status-pill status-pill--success'
  }
  if (status === 'error') {
    return 'status-pill status-pill--error'
  }
  if (status === 'testing') {
    return 'status-pill status-pill--idle'
  }
  return 'status-pill status-pill--warn'
}

function getStatusLabel(status: AsyncStatus, configured: boolean): string {
  if (status === 'testing') {
    return '测试中'
  }
  if (status === 'success') {
    return '测试成功'
  }
  if (status === 'error') {
    return '测试失败'
  }
  return configured ? '已配置' : '未配置'
}

function getSpeechMissingItems(config: AppConfig): string[] {
  if (config.defaultTranscriptionProvider === 'xfyun_speed_transcription') {
    const missing: string[] = []
    if (!safeTrim(config.xfyunSpeedAppId)) missing.push('讯飞 AppID')
    if (!safeTrim(config.xfyunSpeedApiKey)) missing.push('讯飞 APIKey')
    if (!safeTrim(config.xfyunSpeedApiSecret)) missing.push('讯飞 APISecret')
    return missing
  }

  switch (config.defaultTranscriptionProvider) {
    case 'baidu_realtime': {
      const missing: string[] = []
      if (!safeTrim(config.baiduAppId)) missing.push('百度 AppID')
      if (!safeTrim(config.baiduApiKey)) missing.push('百度 API Key')
      if (!safeTrim(config.baiduDevPid)) missing.push('百度识别模型 PID')
      if (!safeTrim(config.baiduCuid)) missing.push('CUID')
      return missing
    }
    case 'baidu_file_async': {
      const missing: string[] = []
      if (!safeTrim(config.baiduFileAppId)) missing.push('百度 AppID')
      if (!safeTrim(config.baiduFileApiKey)) missing.push('百度 API Key')
      if (!safeTrim(config.baiduFileSecretKey)) missing.push('百度 Secret Key')
      return missing
    }
    case 'tencent_realtime': {
      const missing: string[] = []
      if (!safeTrim(config.tencentAppId)) missing.push('腾讯 AppID')
      if (!safeTrim(config.tencentSecretId)) missing.push('腾讯 SecretID')
      if (!safeTrim(config.tencentSecretKey)) missing.push('腾讯 SecretKey')
      if (!safeTrim(config.tencentEngineModelType)) missing.push('引擎模型类型')
      return missing
    }
    case 'tencent_file_async': {
      const missing: string[] = []
      if (!safeTrim(config.tencentFileSecretId)) missing.push('腾讯 SecretID')
      if (!safeTrim(config.tencentFileSecretKey)) missing.push('腾讯 SecretKey')
      if (!safeTrim(config.tencentFileEngineModelType)) missing.push('引擎模型类型')
      return missing
    }
    case 'xfyun_lfasr': {
      const missing: string[] = []
      if (!safeTrim(config.xfyunAppId)) missing.push('讯飞 AppID')
      if (!safeTrim(config.xfyunSecretKey)) missing.push('讯飞 SecretKey')
      return missing
    }
    case 'openaiSpeech': {
      const missing: string[] = []
      if (!safeTrim(config.speechBaseUrl)) missing.push('识别服务地址')
      if (!safeTrim(config.speechApiKey)) missing.push('识别 API Key')
      if (!safeTrim(config.speechModel)) missing.push('识别模型')
      return missing
    }
    case 'localFasterWhisper':
      return []
    default:
      return ['识别配置']
  }
}

function getTranslationMissingItems(config: AppConfig): string[] {
  const missing: string[] = []
  if (!safeTrim(config.baseUrl)) missing.push('翻译服务地址')
  if (!safeTrim(config.apiKey)) missing.push('翻译 API Key')
  if (!safeTrim(config.model)) missing.push('翻译模型')
  return missing
}

function getSpeechProviderHint(provider: TranscriptionProviderName): string {
  if (provider === 'xfyun_lfasr') {
    return '面向 classic/legacy 的讯飞经典长音频转写链路，当前版本先支持配置展示与保存。'
  }

  if (provider === 'xfyun_speed_transcription') {
    return '面向已购的讯飞极速录音转写大模型，当前版本先支持配置展示与保存。'
  }

  switch (provider) {
    case 'baidu_realtime':
      return '适合当前已有的百度实时识别链路，继续保留给现有用户使用。'
    case 'baidu_file_async':
      return '面向后续百度音频文件转写接入。当前这一版先支持在设置页中编辑和保存配置。'
    case 'tencent_realtime':
      return '保留当前腾讯实时识别入口，方便继续兼容现有配置和实时识别调试。'
    case 'tencent_file_async':
      return '面向后续腾讯录音文件识别接入。当前这一版先支持在设置页中编辑和保存配置。'
    case 'xfyun_lfasr':
      return '面向后续讯飞长音频转写接入。当前这一版先支持在设置页中编辑和保存配置。'
    case 'openaiSpeech':
      return '如需继续使用 OpenAI 兼容识别，可在这里填写服务地址、API Key 和模型。'
    case 'localFasterWhisper':
      return '本地识别适合离线场景，但首次使用通常需要准备运行时和本地模型。'
    default:
      return '请先选择识别服务商。'
  }
}

function getSpeechProviderDescription(
  config: AppConfig,
  managedModelRoots: string[],
): string {
  if (config.defaultTranscriptionProvider === 'xfyun_lfasr') {
    return '讯飞经典长音频转写当前仅开放配置展示与保存，测试连接与主流程接入后续补齐。'
  }

  if (config.defaultTranscriptionProvider === 'xfyun_speed_transcription') {
    return '讯飞极速录音转写大模型当前仅开放配置展示与保存，测试连接与主流程接入后续补齐。'
  }

  switch (config.defaultTranscriptionProvider) {
    case 'baidu_realtime':
      return '媒体文件会先预处理为 16k 单声道 PCM，再通过百度实时识别链路发送音频数据。'
    case 'baidu_file_async':
      return '百度音频文件转写当前仅开放配置编辑与保存。测试连接和实际识别逻辑会在后续 provider 实现接入。'
    case 'tencent_realtime':
      return '腾讯实时识别入口继续保留，方便兼容现有配置和实时识别调试。'
    case 'tencent_file_async':
      return '腾讯录音文件识别当前仅开放配置编辑与保存。测试连接和实际识别逻辑会在后续 provider 实现接入。'
    case 'xfyun_lfasr':
      return '讯飞长音频转写当前仅开放配置编辑与保存。测试连接和实际识别逻辑会在后续 provider 实现接入。'
    case 'openaiSpeech':
      return '保留 OpenAI 兼容识别作为兼容入口，适合已经在使用兼容语音接口的用户。'
    case 'localFasterWhisper':
      return managedModelRoots.length > 0
        ? `当前使用本地识别，已记录 ${managedModelRoots.length} 个本地模型目录。`
        : '当前使用本地识别，请回到首页确认 FFmpeg、运行时和本地模型是否已经就绪。'
    default:
      return '请先完成识别配置。'
  }
}

function getSpeechProviderTestHint(provider: TranscriptionProviderName): string | null {
  if (provider === 'xfyun_speed_transcription') {
    return '提示：讯飞极速录音转写大模型当前版本先支持配置展示与保存，测试连接与主流程接入后续补齐。'
  }

  if (FILE_ASYNC_SPEECH_PROVIDERS.has(provider)) {
    return '提示：当前版本先支持保存这些文件异步识别配置。测试连接按钮可能暂未接入对应后端逻辑。'
  }

  return null
}

export function SettingsWorkspace({
  config,
  configError,
  isConfigLoading,
  managedModelRoots,
  currentLanguageLabel,
  isUninstalling,
  uninstallError,
  onSaveConfig,
  onValidateConfig,
  onValidateSpeechConfig,
  onOpenImport,
  onReloadConfig,
  onStartUninstall,
}: SettingsWorkspaceProps) {
  const [draftConfig, setDraftConfig] = useState<AppConfig>(() => config ?? createDefaultAppConfig())
  const [isSaving, setIsSaving] = useState(false)
  const [saveFeedback, setSaveFeedback] = useState<AsyncFeedback>(createIdleFeedback)
  const [speechFeedback, setSpeechFeedback] = useState<AsyncFeedback>(createIdleFeedback)
  const [translationFeedback, setTranslationFeedback] = useState<AsyncFeedback>(createIdleFeedback)

  useEffect(() => {
    setDraftConfig(config ?? createDefaultAppConfig())
  }, [config])

  const pageBusy = isConfigLoading || isSaving
  const speechConfigured = Boolean(hasUsableSpeechConfig(draftConfig))
  const translationConfigured = Boolean(hasUsableTranslationConfig(draftConfig))
  const speechMissingItems = useMemo(() => getSpeechMissingItems(draftConfig), [draftConfig])
  const translationMissingItems = useMemo(
    () => getTranslationMissingItems(draftConfig),
    [draftConfig],
  )
  const speechProviderTestHint = getSpeechProviderTestHint(draftConfig.defaultTranscriptionProvider)

  async function handleSave() {
    setIsSaving(true)
    setSaveFeedback({ status: 'testing', message: '正在保存配置，请稍候…' })

    try {
      await onSaveConfig({
        ...draftConfig,
        speechProvider: draftConfig.defaultTranscriptionProvider,
      })
      setSaveFeedback({
        status: 'success',
        message: '配置已保存。现在可以返回首页导入媒体或字幕文件，直接验证主流程。',
      })
    } catch (error) {
      console.error('LinguaSub failed to save settings.', error)
      setSaveFeedback({
        status: 'error',
        message: error instanceof Error ? error.message : '保存失败，请检查输入内容后重试。',
      })
    } finally {
      setIsSaving(false)
    }
  }

  async function handleValidateSpeech() {
    if (isLocalSpeechProvider(draftConfig.defaultTranscriptionProvider)) {
      setSpeechFeedback({
        status: 'success',
        message: '当前已切换到本地识别模式，无需测试云端连接。请回到首页查看本地运行时和模型状态。',
      })
      return
    }

    if (draftConfig.defaultTranscriptionProvider === 'xfyun_speed_transcription') {
      setSpeechFeedback({
        status: 'idle',
        message:
          '讯飞极速录音转写大模型当前版本先支持配置展示与保存，测试连接与主流程接入后续补齐。',
      })
      return
    }

    if (!speechConfigured) {
      setSpeechFeedback({
        status: 'error',
        message: `识别配置还不完整，请先补全：${speechMissingItems.join('、')}。`,
      })
      return
    }

    setSpeechFeedback({ status: 'testing', message: '正在测试识别连接，请稍候…' })
    try {
      const message = await onValidateSpeechConfig({
        ...draftConfig,
        speechProvider: draftConfig.defaultTranscriptionProvider,
      })
      setSpeechFeedback({ status: 'success', message })
    } catch (error) {
      console.error('LinguaSub failed to validate speech config.', error)
      setSpeechFeedback({
        status: 'error',
        message: error instanceof Error ? error.message : '识别连接测试失败。',
      })
    }
  }

  async function handleValidateTranslation() {
    if (!translationConfigured) {
      setTranslationFeedback({
        status: 'error',
        message: `翻译配置还不完整，请先补全：${translationMissingItems.join('、')}。`,
      })
      return
    }

    setTranslationFeedback({ status: 'testing', message: '正在测试翻译连接，请稍候…' })
    try {
      const message = await onValidateConfig(draftConfig)
      setTranslationFeedback({ status: 'success', message })
    } catch (error) {
      console.error('LinguaSub failed to validate translation config.', error)
      setTranslationFeedback({
        status: 'error',
        message: error instanceof Error ? error.message : '翻译连接测试失败。',
      })
    }
  }

  async function handleUninstall() {
    try {
      await onStartUninstall()
    } catch (error) {
      console.error('LinguaSub failed to start uninstall.', error)
    }
  }

  return (
    <>
      <SectionCard
        eyebrow="设置"
        title="服务与接口配置"
        description="将语音识别和字幕翻译拆分配置，方便快速看清当前缺少的是哪一块。"
        className="span-12"
      >
        <div className="summary-grid">
          <div className="summary-item">
            <span className="summary-item__label">界面语言</span>
            <span className="summary-item__value">{currentLanguageLabel}</span>
          </div>
          <div className="summary-item">
            <span className="summary-item__label">识别状态</span>
            <span className={getStatusClassName(speechFeedback.status, speechConfigured)}>
              {getStatusLabel(speechFeedback.status, speechConfigured)}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-item__label">翻译状态</span>
            <span className={getStatusClassName(translationFeedback.status, translationConfigured)}>
              {getStatusLabel(translationFeedback.status, translationConfigured)}
            </span>
          </div>
        </div>

        {configError ? (
          <div className="warning-banner" role="alert">
            <strong>配置读取异常</strong>
            <p>{configError}</p>
          </div>
        ) : null}
      </SectionCard>

      <SectionCard
        eyebrow="语音识别配置"
        title="把视频或音频转成原文字幕"
        description="先选择识别服务商，再填写这个 provider 所需的鉴权信息和模型参数。"
        className="span-7"
      >
        <div className="settings-config-card">
          <div className="settings-config-card__header">
            <div>
              <h3>语音识别配置</h3>
              <p>{getSpeechProviderHint(draftConfig.defaultTranscriptionProvider)}</p>
            </div>
            <span className={getStatusClassName(speechFeedback.status, speechConfigured)}>
              {getStatusLabel(speechFeedback.status, speechConfigured)}
            </span>
          </div>

          <div className="settings-grid">
            <label className="field-block">
              <span className="field-label">识别服务商</span>
              <select
                className="select-input"
                value={draftConfig.defaultTranscriptionProvider}
                disabled={pageBusy}
                onChange={(event) => {
                  setDraftConfig((current) =>
                    updateDefaultTranscriptionProvider(
                      current,
                      event.target.value as TranscriptionProviderName,
                    ),
                  )
                  setSpeechFeedback(createIdleFeedback())
                }}
              >
                {TRANSCRIPTION_PROVIDER_OPTIONS.map((provider) => (
                  <option key={provider} value={provider}>
                    {TRANSCRIPTION_PROVIDER_LABELS[provider]}
                  </option>
                ))}
              </select>
            </label>

            {draftConfig.defaultTranscriptionProvider === 'baidu_realtime' ? (
              <>
                <label className="field-block">
                  <span className="field-label">百度 AppID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.baiduAppId}
                    disabled={pageBusy}
                    placeholder="输入百度 AppID"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduAppId: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">百度 API Key</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.baiduApiKey}
                    disabled={pageBusy}
                    placeholder="输入百度 API Key"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduApiKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">百度识别模型 PID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.baiduDevPid}
                    disabled={pageBusy}
                    placeholder="例如：15372"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduDevPid: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">CUID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.baiduCuid}
                    disabled={pageBusy}
                    placeholder="例如：linguasub-desktop"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduCuid: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>
              </>
            ) : null}

            {draftConfig.defaultTranscriptionProvider === 'baidu_file_async' ? (
              <>
                <label className="field-block">
                  <span className="field-label">百度 AppID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.baiduFileAppId}
                    disabled={pageBusy}
                    placeholder="输入百度 AppID"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduFileAppId: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">百度 API Key</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.baiduFileApiKey}
                    disabled={pageBusy}
                    placeholder="输入百度 API Key"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduFileApiKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">百度 Secret Key</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.baiduFileSecretKey}
                    disabled={pageBusy}
                    placeholder="输入百度 Secret Key"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduFileSecretKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">百度识别模型 PID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.baiduFileDevPid}
                    disabled={pageBusy}
                    placeholder="例如：15372"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { baiduFileDevPid: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>
              </>
            ) : null}

            {draftConfig.defaultTranscriptionProvider === 'tencent_realtime' ? (
              <>
                <label className="field-block">
                  <span className="field-label">腾讯 AppID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.tencentAppId}
                    disabled={pageBusy}
                    placeholder="输入腾讯 AppID"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { tencentAppId: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">腾讯 SecretID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.tencentSecretId}
                    disabled={pageBusy}
                    placeholder="输入腾讯 SecretID"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { tencentSecretId: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">腾讯 SecretKey</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.tencentSecretKey}
                    disabled={pageBusy}
                    placeholder="输入腾讯 SecretKey"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { tencentSecretKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">引擎模型类型</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.tencentEngineModelType}
                    disabled={pageBusy}
                    placeholder="例如：16k_zh"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, {
                          tencentEngineModelType: event.target.value,
                        }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>
              </>
            ) : null}

            {draftConfig.defaultTranscriptionProvider === 'tencent_file_async' ? (
              <>
                <label className="field-block">
                  <span className="field-label">腾讯 SecretID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.tencentFileSecretId}
                    disabled={pageBusy}
                    placeholder="输入腾讯 SecretID"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { tencentFileSecretId: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">腾讯 SecretKey</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.tencentFileSecretKey}
                    disabled={pageBusy}
                    placeholder="输入腾讯 SecretKey"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { tencentFileSecretKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">引擎模型类型</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.tencentFileEngineModelType}
                    disabled={pageBusy}
                    placeholder="例如：16k_zh"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, {
                          tencentFileEngineModelType: event.target.value,
                        }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>
              </>
            ) : null}

            {draftConfig.defaultTranscriptionProvider === 'xfyun_lfasr' ? (
              <>
                <label className="field-block">
                  <span className="field-label">讯飞 AppID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.xfyunAppId}
                    disabled={pageBusy}
                    placeholder="输入讯飞 AppID"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { xfyunAppId: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">讯飞 SecretKey</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.xfyunSecretKey}
                    disabled={pageBusy}
                    placeholder="输入讯飞 SecretKey"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { xfyunSecretKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>
              </>
            ) : null}

            {draftConfig.defaultTranscriptionProvider === 'xfyun_speed_transcription' ? (
              <>
                <label className="field-block">
                  <span className="field-label">讯飞 AppID</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.xfyunSpeedAppId}
                    disabled={pageBusy}
                    placeholder="输入讯飞 AppID"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { xfyunSpeedAppId: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">讯飞 APIKey</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.xfyunSpeedApiKey}
                    disabled={pageBusy}
                    placeholder="输入讯飞 APIKey"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { xfyunSpeedApiKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">讯飞 APISecret</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.xfyunSpeedApiSecret}
                    disabled={pageBusy}
                    placeholder="输入讯飞 APISecret"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, {
                          xfyunSpeedApiSecret: event.target.value,
                        }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>
              </>
            ) : null}

            {draftConfig.defaultTranscriptionProvider === 'openaiSpeech' ? (
              <>
                <label className="field-block">
                  <span className="field-label">识别服务地址</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.speechBaseUrl}
                    disabled={pageBusy}
                    placeholder="例如：https://api.openai.com/v1"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { speechBaseUrl: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">识别 API Key</span>
                  <input
                    className="text-input"
                    type="password"
                    value={draftConfig.speechApiKey}
                    disabled={pageBusy}
                    placeholder="输入识别 API Key"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { speechApiKey: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>

                <label className="field-block">
                  <span className="field-label">识别模型</span>
                  <input
                    className="text-input"
                    type="text"
                    value={draftConfig.speechModel}
                    disabled={pageBusy}
                    placeholder="例如：whisper-1"
                    onChange={(event) => {
                      setDraftConfig((current) =>
                        updateSpeechConfig(current, { speechModel: event.target.value }),
                      )
                      setSpeechFeedback(createIdleFeedback())
                    }}
                  />
                </label>
              </>
            ) : null}

            {draftConfig.defaultTranscriptionProvider === 'localFasterWhisper' ? (
              <div className="info-panel">
                <strong>本地识别说明</strong>
                <p>
                  本地识别不依赖云端 API。请回到首页查看 FFmpeg、运行时和本地模型是否已经就绪。
                </p>
              </div>
            ) : null}
          </div>

          <div className="settings-config-card__footer">
            <div className="info-panel">
              <strong>当前配置说明</strong>
              <p>{getSpeechProviderDescription(draftConfig, managedModelRoots)}</p>
              {speechProviderTestHint ? <p>{speechProviderTestHint}</p> : null}
              {!speechConfigured && !isLocalSpeechProvider(draftConfig.defaultTranscriptionProvider) ? (
                <p>当前还缺：{speechMissingItems.join('、')}。</p>
              ) : null}
            </div>

            {speechFeedback.message ? (
              <div
                className={
                  speechFeedback.status === 'error'
                    ? 'error-banner'
                    : speechFeedback.status === 'success'
                      ? 'success-banner'
                      : 'warning-banner'
                }
                role="alert"
              >
                <strong>{getStatusLabel(speechFeedback.status, speechConfigured)}</strong>
                <p>{speechFeedback.message}</p>
              </div>
            ) : null}

            <div className="inline-actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={() => {
                  void handleValidateSpeech()
                }}
                disabled={pageBusy || speechFeedback.status === 'testing'}
              >
                {speechFeedback.status === 'testing' ? '测试中…' : '测试识别连接'}
              </button>
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="字幕翻译配置"
        title="把原文字幕翻译成目标语言"
        description="这一组配置只影响翻译服务，不会改变识别 provider。"
        className="span-5"
      >
        <div className="settings-config-card">
          <div className="settings-config-card__header">
            <div>
              <h3>字幕翻译配置</h3>
              <p>翻译主流程会直接读取这里保存的服务商、地址、API Key 和模型。</p>
            </div>
            <span className={getStatusClassName(translationFeedback.status, translationConfigured)}>
              {getStatusLabel(translationFeedback.status, translationConfigured)}
            </span>
          </div>

          <div className="settings-grid">
            <label className="field-block">
              <span className="field-label">翻译服务商</span>
              <select
                className="select-input"
                value={draftConfig.defaultProvider}
                disabled={pageBusy}
                onChange={(event) => {
                  setDraftConfig((current) =>
                    selectProvider(current, event.target.value as ProviderName),
                  )
                  setTranslationFeedback(createIdleFeedback())
                }}
              >
                {(Object.keys(PROVIDER_LABELS) as ProviderName[]).map((provider) => (
                  <option key={provider} value={provider}>
                    {PROVIDER_LABELS[provider]}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-block">
              <span className="field-label">翻译服务地址</span>
              <input
                className="text-input"
                type="text"
                value={draftConfig.baseUrl}
                disabled={pageBusy}
                placeholder="例如：https://api.openai.com/v1"
                onChange={(event) => {
                  setDraftConfig((current) =>
                    updateActiveProviderConfig(current, { baseUrl: event.target.value }),
                  )
                  setTranslationFeedback(createIdleFeedback())
                }}
              />
            </label>

            <label className="field-block">
              <span className="field-label">翻译 API Key</span>
              <input
                className="text-input"
                type="password"
                value={draftConfig.apiKey}
                disabled={pageBusy}
                placeholder="输入翻译 API Key"
                onChange={(event) => {
                  setDraftConfig((current) =>
                    updateActiveProviderConfig(current, { apiKey: event.target.value }),
                  )
                  setTranslationFeedback(createIdleFeedback())
                }}
              />
            </label>

            <label className="field-block">
              <span className="field-label">翻译模型</span>
              <input
                className="text-input"
                type="text"
                value={draftConfig.model}
                disabled={pageBusy}
                placeholder="例如：gpt-4o-mini"
                onChange={(event) => {
                  setDraftConfig((current) =>
                    updateActiveProviderConfig(current, { model: event.target.value }),
                  )
                  setTranslationFeedback(createIdleFeedback())
                }}
              />
            </label>

            <label className="field-block">
              <span className="field-label">输出方式</span>
              <select
                className="select-input"
                value={draftConfig.outputMode}
                disabled={pageBusy}
                onChange={(event) => {
                  setDraftConfig((current) =>
                    updateOutputMode(current, event.target.value as OutputMode),
                  )
                  setTranslationFeedback(createIdleFeedback())
                }}
              >
                {(Object.keys(OUTPUT_MODE_LABELS) as OutputMode[]).map((mode) => (
                  <option key={mode} value={mode}>
                    {OUTPUT_MODE_LABELS[mode]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="settings-config-card__footer">
            <div className="info-panel">
              <strong>当前翻译配置说明</strong>
              <p>
                当前已选翻译服务商：{PROVIDER_LABELS[draftConfig.defaultProvider]}。本版本默认将原文翻译为中文。
              </p>
              {!translationConfigured ? (
                <p>当前还缺：{translationMissingItems.join('、')}。</p>
              ) : null}
            </div>

            {translationFeedback.message ? (
              <div
                className={
                  translationFeedback.status === 'error'
                    ? 'error-banner'
                    : translationFeedback.status === 'success'
                      ? 'success-banner'
                      : 'warning-banner'
                }
                role="alert"
              >
                <strong>{getStatusLabel(translationFeedback.status, translationConfigured)}</strong>
                <p>{translationFeedback.message}</p>
              </div>
            ) : null}

            <div className="inline-actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={() => {
                  void handleValidateTranslation()
                }}
                disabled={pageBusy || translationFeedback.status === 'testing'}
              >
                {translationFeedback.status === 'testing' ? '测试中…' : '测试翻译连接'}
              </button>
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow="维护"
        title="保存、验证与卸载"
        description="底部统一提供保存、重新读取配置和卸载入口。"
        className="span-12"
      >
        {saveFeedback.message ? (
          <div
            className={
              saveFeedback.status === 'error'
                ? 'error-banner'
                : saveFeedback.status === 'success'
                  ? 'success-banner'
                  : 'warning-banner'
            }
            role="alert"
          >
            <strong>{getStatusLabel(saveFeedback.status, true)}</strong>
            <p>{saveFeedback.message}</p>
          </div>
        ) : null}

        {uninstallError ? (
          <div className="error-banner" role="alert">
            <strong>卸载启动失败</strong>
            <p>{uninstallError}</p>
          </div>
        ) : null}

        <div className="inline-actions">
          <button
            type="button"
            className="button button--secondary"
            onClick={onReloadConfig}
            disabled={pageBusy}
          >
            {isConfigLoading ? '读取中…' : '重新读取配置'}
          </button>
          <button
            type="button"
            className="button button--secondary"
            onClick={onOpenImport}
            disabled={pageBusy}
          >
            返回首页验证
          </button>
          <button
            type="button"
            className="button button--danger"
            onClick={() => {
              void handleUninstall()
            }}
            disabled={isUninstalling}
          >
            {isUninstalling ? '正在启动卸载…' : '卸载 LinguaSub'}
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={() => {
              void handleSave()
            }}
            disabled={pageBusy}
          >
            {isSaving ? '保存中…' : '保存全部配置'}
          </button>
        </div>
      </SectionCard>
    </>
  )
}
