import type {
  AppConfig,
  AsrModelSize,
  LanguageCode,
  OutputMode,
  ProjectState,
  ProviderName,
  TranscriptionProviderName,
} from '../types/models'
import { useI18n } from '../i18n/useI18n'
import type { ImportResult } from '../types/import'
import type {
  AsrInputLanguage,
  AsrQualityPreset,
  TranscriptionDiagnostics,
} from '../types/transcription'
import type { TaskLogEntry } from '../types/tasks'
import { hasUsableTranslationConfig, isCloudSpeechProvider } from '../utils/config'
import { SectionCard } from './SectionCard'
import { TaskLogPanel } from './TaskLogPanel'

type TranslationWorkspaceProps = {
  config: AppConfig | null
  configError: string | null
  importResult: ImportResult | null
  projectState: ProjectState
  transcriptionRun: TranscriptionDiagnostics | null
  isConfigLoading: boolean
  isWorking: boolean
  processError: string | null
  taskLogs: TaskLogEntry[]
  selectedTranscriptionProvider: TranscriptionProviderName
  speechConfigReady: boolean
  selectedAsrModelSize: AsrModelSize
  selectedAsrLanguage: AsrInputLanguage
  selectedAsrQualityPreset: AsrQualityPreset
  onProviderChange: (provider: ProviderName) => void
  onModelChange: (model: string) => void
  onOutputModeChange: (mode: OutputMode) => void
  onOpenSettings: () => void
  onReloadConfig: () => void
}

function getTranslationReadiness(
  importResult: ImportResult | null,
  segmentCount: number,
  languagePack: ReturnType<typeof useI18n>['m'],
): string {
  if (!importResult) {
    return languagePack.translationPage.readinessNeedImport
  }

  if (segmentCount > 0) {
    return languagePack.translationPage.readinessPreparedSegments(segmentCount)
  }

  return importResult.route === 'recognition'
    ? languagePack.translationPage.readinessRecognition
    : languagePack.translationPage.readinessSrt
}

function getRouteLabel(
  importResult: ImportResult | null,
  languagePack: ReturnType<typeof useI18n>['m'],
): string {
  if (!importResult) {
    return languagePack.translationPage.routeWaiting
  }

  return importResult.route === 'recognition'
    ? languagePack.translationPage.routeRecognition
    : languagePack.translationPage.routeSrt
}

function getAsrLanguageLabel(
  language: AsrInputLanguage,
  languagePack: ReturnType<typeof useI18n>['m'],
): string {
  return languagePack.common.asrLanguages[language]
}

function getAsrQualityLabel(
  preset: AsrQualityPreset,
  languagePack: ReturnType<typeof useI18n>['m'],
): string {
  return languagePack.common.asrQualityPresets[preset]
}

function getTranscriptionProviderLabel(
  provider: TranscriptionProviderName,
  languagePack: ReturnType<typeof useI18n>['m'],
): string {
  const labels = (
    languagePack.common as { transcriptionProviders?: Record<string, string> }
  ).transcriptionProviders
  return (
    labels?.[provider] ??
    (provider === 'baidu_realtime'
      ? '百度实时识别（推荐）'
      : provider === 'tencent_realtime'
        ? '腾讯实时识别（预留）'
        : provider === 'openaiSpeech'
          ? 'OpenAI 兼容识别'
          : '本地识别（进阶 / 离线）')
  )
}

function getDetectedLanguageLabel(
  language: LanguageCode,
  languagePack: ReturnType<typeof useI18n>['m'],
): string {
  if (language === 'zh-CN') {
    return languagePack.common.asrLanguages.zh
  }

  if (language === 'auto') {
    return languagePack.common.asrLanguages.auto
  }

  return languagePack.common.asrLanguages[language]
}

export function TranslationWorkspace({
  config,
  configError,
  importResult,
  projectState,
  transcriptionRun,
  isConfigLoading,
  isWorking,
  processError,
  taskLogs,
  selectedTranscriptionProvider,
  speechConfigReady,
  selectedAsrModelSize,
  selectedAsrLanguage,
  selectedAsrQualityPreset,
  onProviderChange,
  onModelChange,
  onOutputModeChange,
  onOpenSettings,
  onReloadConfig,
}: TranslationWorkspaceProps) {
  const { m } = useI18n()
  const translationCopy = {
    transcriptionProviderLabel:
      (
        m.translationPage as {
          transcriptionProviderLabel?: string
          cloudSpeechConfigured?: string
          cloudSpeechMissing?: string
          localSpeechConfigured?: string
          cloudSpeechNeededTitle?: string
          cloudSpeechNeededDescription?: string
          cloudRecognitionSummarySettings?: (model: string, language: string) => string
          cloudRawQualityPending?: string
        }
      ).transcriptionProviderLabel ?? 'Transcription route',
    cloudSpeechConfigured:
      (
        m.translationPage as {
          cloudSpeechConfigured?: string
        }
      ).cloudSpeechConfigured ?? '云端识别配置已就绪，可以直接用于媒体识别。',
    cloudSpeechMissing:
      (
        m.translationPage as {
          cloudSpeechMissing?: string
        }
      ).cloudSpeechMissing ?? '当前云端识别配置还不完整，请先补齐当前 provider 所需的鉴权与模型参数。',
    localSpeechConfigured:
      (
        m.translationPage as {
          localSpeechConfigured?: string
        }
      ).localSpeechConfigured ??
      'Local transcription uses bundled FFmpeg, faster-whisper, and downloaded local models.',
    cloudSpeechNeededTitle:
      (
        m.translationPage as {
          cloudSpeechNeededTitle?: string
        }
      ).cloudSpeechNeededTitle ?? '云端识别需要先完成配置',
    cloudSpeechNeededDescription:
      (
        m.translationPage as {
          cloudSpeechNeededDescription?: string
        }
      ).cloudSpeechNeededDescription ??
      '请先打开设置页，保存当前识别 provider 所需的鉴权信息、服务地址或模型参数，再开始媒体识别。',
    cloudRecognitionSummarySettings:
      (
        m.translationPage as {
          cloudRecognitionSummarySettings?: (model: string, language: string) => string
        }
      ).cloudRecognitionSummarySettings ??
      ((model: string, language: string) =>
        `Current cloud recognition plan: ${model} / ${language}.`),
    cloudRawQualityPending:
      (
        m.translationPage as {
          cloudRawQualityPending?: string
        }
      ).cloudRawQualityPending ??
      '云端识别尚未开始。原始识别质量将取决于当前识别 provider 的模型参数和语言提示。',
  }
  const activeProvider =
    config?.apiProviders.find((provider) => provider.provider === config.defaultProvider) ?? null
  const routeLabel = getRouteLabel(importResult, m)
  const apiReady = hasUsableTranslationConfig(config)
  const cloudSpeechReady = speechConfigReady
  const cloudProviderModel = (() => {
    if (!config) {
      return '未配置'
    }
    switch (selectedTranscriptionProvider) {
      case 'baidu_realtime':
        return config.baiduDevPid || '未配置'
      case 'tencent_realtime':
        return config.tencentEngineModelType || '未配置'
      case 'openaiSpeech':
        return config.speechModel || '未配置'
      default:
        return selectedAsrModelSize
    }
  })()

  return (
    <>
      <SectionCard
        eyebrow={m.translationPage.sections.translation.eyebrow}
        title={m.translationPage.sections.translation.title}
        description={m.translationPage.sections.translation.description}
        className="span-7"
      >
        {isConfigLoading ? (
          <div className="empty-state">
            <h3>{m.translationPage.loadingConfigTitle}</h3>
            <p>{m.translationPage.loadingConfigDescription}</p>
          </div>
        ) : config ? (
          <div className="settings-grid">
            <label className="field-block">
              <span className="field-label">{m.common.misc.provider}</span>
              <select
                className="select-input"
                value={config.defaultProvider}
                onChange={(event) => onProviderChange(event.target.value as ProviderName)}
              >
                {config.apiProviders.map((provider) => (
                  <option key={provider.provider} value={provider.provider}>
                    {m.common.providers[provider.provider]}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-block">
              <span className="field-label">{m.common.misc.model}</span>
              <input
                className="text-input"
                type="text"
                value={config.model}
                onChange={(event) => onModelChange(event.target.value)}
                placeholder={m.common.placeholders.model}
                spellCheck={false}
              />
            </label>

            <label className="field-block">
              <span className="field-label">{m.common.summary.outputMode}</span>
              <select
                className="select-input"
                value={config.outputMode}
                onChange={(event) => onOutputModeChange(event.target.value as OutputMode)}
              >
                <option value="bilingual">{m.common.outputModes.bilingual}</option>
                <option value="single">{m.common.outputModes.single}</option>
              </select>
            </label>

            <div className="info-tile">
              <span className="field-label">{m.common.misc.baseUrl}</span>
              <strong>{config.baseUrl}</strong>
              <p>
                {activeProvider?.provider === 'deepseek'
                  ? m.translationPage.deepseekProvider
                  : m.translationPage.openaiCompatibleProvider}
              </p>
            </div>

            <div className="info-tile">
              <span className="field-label">{m.common.misc.apiKey}</span>
              <strong>{config.apiKey ? m.common.misc.configured : m.common.misc.missing}</strong>
              <p>
                {config.apiKey
                  ? m.translationPage.providerConfigured
                  : m.translationPage.providerMissingApiKey}
              </p>
            </div>

            <div className="info-tile">
              <span className="field-label">{m.common.misc.currentRoute}</span>
              <strong>{routeLabel}</strong>
              <p>{getTranslationReadiness(importResult, projectState.segments.length, m)}</p>
            </div>

            <div className="info-tile">
              <span className="field-label">
                {translationCopy.transcriptionProviderLabel}
              </span>
              <strong>{getTranscriptionProviderLabel(selectedTranscriptionProvider, m)}</strong>
              <p>
                {isCloudSpeechProvider(selectedTranscriptionProvider)
                  ? cloudSpeechReady
                    ? translationCopy.cloudSpeechConfigured
                    : translationCopy.cloudSpeechMissing
                  : translationCopy.localSpeechConfigured}
              </p>
            </div>
          </div>
        ) : (
          <div className="empty-state">
            <h3>{m.translationPage.configUnavailableTitle}</h3>
            <p>{m.translationPage.configUnavailableDescription}</p>
          </div>
        )}

        {configError ? (
          <div className="error-banner" role="alert">
            <strong>{m.common.misc.configError}</strong>
            <p>{configError}</p>
          </div>
        ) : null}

        {!isConfigLoading && config && !apiReady ? (
          <div className="warning-banner" role="alert">
            <strong>{m.translationPage.apiConfigNeededTitle}</strong>
            <p>{m.translationPage.apiConfigNeededDescription}</p>
            <div className="inline-actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={onOpenSettings}
                disabled={isWorking}
              >
                {m.translationPage.openSettingsAction}
              </button>
            </div>
          </div>
        ) : null}

        {!isConfigLoading &&
        config &&
        isCloudSpeechProvider(selectedTranscriptionProvider) &&
        !cloudSpeechReady ? (
          <div className="warning-banner" role="alert">
            <strong>{translationCopy.cloudSpeechNeededTitle}</strong>
            <p>{translationCopy.cloudSpeechNeededDescription}</p>
            <div className="inline-actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={onOpenSettings}
                disabled={isWorking}
              >
                {m.translationPage.openSettingsAction}
              </button>
            </div>
          </div>
        ) : null}

        {processError ? (
          <div className="error-banner" role="alert">
            <strong>{m.common.misc.translationFlowFailed}</strong>
            <p>{processError}</p>
            {config &&
            (!apiReady ||
              (isCloudSpeechProvider(selectedTranscriptionProvider) && !cloudSpeechReady)) ? (
              <div className="inline-actions">
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={onOpenSettings}
                  disabled={isWorking}
                >
                  {m.translationPage.openSettingsAction}
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="inline-actions">
          <button
            type="button"
            className="button button--secondary"
            onClick={onReloadConfig}
            disabled={isConfigLoading || isWorking}
          >
            {isConfigLoading ? m.common.misc.loading : m.common.buttons.reloadConfig}
          </button>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow={m.translationPage.sections.source.eyebrow}
        title={m.translationPage.sections.source.title}
        description={m.translationPage.sections.source.description}
        className="span-5"
      >
        {importResult ? (
          <>
            <div className="summary-grid">
              <div className="summary-item">
                <span className="summary-item__label">{m.common.summary.file}</span>
                <span className="summary-item__value">{importResult.currentFile.name}</span>
              </div>
              <div className="summary-item">
                <span className="summary-item__label">{m.common.summary.route}</span>
                <span className="summary-item__value">{routeLabel}</span>
              </div>
              <div className="summary-item">
                <span className="summary-item__label">{m.common.misc.preparedSegments}</span>
                <span className="summary-item__value">{projectState.segments.length}</span>
              </div>
              <div className="summary-item">
                <span className="summary-item__label">{m.common.summary.projectStatus}</span>
                <span className="summary-item__value">
                  {m.common.statuses[projectState.status]}
                </span>
              </div>
            </div>

            {importResult.route === 'recognition' ? (
              <div className="info-panel">
                <strong>{m.translationPage.recognitionSummaryTitle}</strong>
                <p>
                  {isCloudSpeechProvider(selectedTranscriptionProvider)
                    ? translationCopy.cloudRecognitionSummarySettings(
                        cloudProviderModel,
                        getAsrLanguageLabel(selectedAsrLanguage, m),
                      )
                    : m.translationPage.recognitionSummarySettings(
                        selectedAsrModelSize,
                        getAsrQualityLabel(selectedAsrQualityPreset, m),
                        getAsrLanguageLabel(selectedAsrLanguage, m),
                      )}
                </p>
                {transcriptionRun ? (
                  <ul className="notice-list">
                    <li>
                      {m.translationPage.rawQualitySummary(
                        transcriptionRun.model,
                        transcriptionRun.provider === 'localFasterWhisper'
                          ? getAsrQualityLabel(
                              transcriptionRun.qualityPreset as AsrQualityPreset,
                              m,
                            )
                          : getTranscriptionProviderLabel(transcriptionRun.provider, m),
                        getAsrLanguageLabel(transcriptionRun.requestedLanguage, m),
                        getDetectedLanguageLabel(transcriptionRun.detectedLanguage, m),
                      )}
                    </li>
                    <li>
                      {m.translationPage.readabilitySummary(
                        transcriptionRun.rawSegmentCount,
                        transcriptionRun.finalSegmentCount,
                      )}
                    </li>
                    {transcriptionRun.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                    <li>{m.translationPage.translationBoundaryNote}</li>
                  </ul>
                ) : (
                  <ul className="notice-list">
                    <li>
                      {isCloudSpeechProvider(selectedTranscriptionProvider)
                        ? translationCopy.cloudRawQualityPending
                        : m.translationPage.rawQualityPending}
                    </li>
                    <li>{m.translationPage.readabilityPending}</li>
                    <li>{m.translationPage.translationBoundaryNote}</li>
                  </ul>
                )}
              </div>
            ) : null}
          </>
        ) : (
          <div className="empty-state">
            <h3>{m.translationPage.noImportedFileTitle}</h3>
            <p>{m.translationPage.noImportedFileDescription}</p>
          </div>
        )}
      </SectionCard>

      <SectionCard
        eyebrow={m.translationPage.sections.progress.eyebrow}
        title={m.translationPage.sections.progress.title}
        description={m.translationPage.sections.progress.description}
        className="span-7"
      >
        <div className="progress-list">
          <article className={`progress-item ${importResult ? 'progress-item--done' : ''}`.trim()}>
            <span className="progress-item__title">1. {m.common.misc.import}</span>
            <p>
              {importResult
                ? m.translationPage.progressImportDone(importResult.currentFile.name)
                : m.translationPage.progressImportWaiting}
            </p>
          </article>
          <article
            className={`progress-item ${
              projectState.status === 'transcribing' || projectState.segments.length > 0
                ? 'progress-item--active'
                : ''
            }`.trim()}
          >
            <span className="progress-item__title">
              2.{' '}
              {importResult?.route === 'translation'
                ? m.common.workflowSteps.SRT
                : m.common.workflowSteps.Recognition}
            </span>
            <p>
              {importResult?.route === 'translation'
                ? projectState.segments.length > 0
                  ? m.translationPage.progressSrtReady
                  : m.translationPage.progressSrtPending
                : projectState.segments.length > 0
                  ? m.translationPage.progressRecognitionReady
                  : m.translationPage.progressRecognitionPending}
            </p>
          </article>
          <article
            className={`progress-item ${
              projectState.status === 'translating' || projectState.status === 'done'
                ? 'progress-item--active'
                : ''
            }`.trim()}
          >
            <span className="progress-item__title">3. {m.common.misc.translation}</span>
            <p>
              {projectState.status === 'done'
                ? m.translationPage.progressTranslationDone
                : m.translationPage.progressTranslationPending}
            </p>
          </article>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow={m.translationPage.sections.translation.eyebrow}
        title={getLogPanelTitle(m)}
        description={getLogPanelDescription(m)}
        className="span-5"
      >
        <TaskLogPanel
          logs={taskLogs}
          title={getLogPanelTitle(m)}
          description={getLogPanelDescription(m)}
          emptyTitle={m.common.misc.waiting}
          emptyDescription={getEmptyLogDescription(m)}
        />
      </SectionCard>
    </>
  )
}

function getLogPanelTitle(m: ReturnType<typeof useI18n>['m']): string {
  return (m.translationPage as { logPanelTitle?: string }).logPanelTitle ?? 'Processing logs'
}

function getLogPanelDescription(m: ReturnType<typeof useI18n>['m']): string {
  return (
    (m.translationPage as { logPanelDescription?: string }).logPanelDescription ??
    'Logs stay collapsed by default so users are not distracted during normal processing.'
  )
}

function getEmptyLogDescription(m: ReturnType<typeof useI18n>['m']): string {
  return (
    (m.translationPage as { logPanelEmptyDescription?: string }).logPanelEmptyDescription ??
    'Once processing starts, LinguaSub will record media loading, recognition, translation, and failure reasons here.'
  )
}
