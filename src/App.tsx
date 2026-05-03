import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'

import { ActionBar } from './components/ActionBar'
import { CommandAgentWorkspace } from './components/CommandAgentWorkspace'
import { ExportWorkspace } from './components/ExportWorkspace'
import { ImportWorkspace } from './components/ImportWorkspace'
import { SettingsWorkspace } from './components/SettingsWorkspace'
import { Sidebar } from './components/Sidebar'
import { SubtitlePreviewWorkspace } from './components/SubtitlePreviewWorkspace'
import { StepHeader } from './components/StepHeader'
import { TranslationWorkspace } from './components/TranslationWorkspace'
import { VideoSubtitleWorkspace } from './components/VideoSubtitleWorkspace'
import {
  sidebarItemKeys,
  type HeaderMetric,
  type SidebarItemKey,
  type SidebarStatus,
} from './data/workflow'
import { useI18n } from './i18n/useI18n'
import {
  buildAgentSegmentSignature,
  type AgentSessionState,
  type ContentSummaryResult,
  type SubtitleQualityResult,
} from './types/agent'
import type {
  CommandAgentSessionItem,
  CommandAgentState,
} from './types/commandAgent'
import {
  loadConfig,
  saveConfig,
  updateConfig,
  validateConfig,
  validateSpeechConfig,
} from './services/configService'
import {
  checkPathExists,
  openPathInFileManager,
  startUninstall,
} from './services/desktopService'
import {
  loadEnvironmentCheck,
  startSpeechModelDownload,
  type SpeechModelDownloadRequest,
} from './services/environmentService'
import {
  exportContentSummaryWord,
  exportSubtitles,
} from './services/exportService'
import { pickVideoSavePath } from './services/saveFilePickerService'
import { loadTaskHistory, upsertTaskHistoryRecord } from './services/taskHistoryService'
import { parseSrt } from './services/srtService'
import { transcribeMedia } from './services/transcriptionService'
import { requestTranslation } from './services/translationService'
import {
  VideoBurnExportConnectionError,
  exportBurnedSubtitleVideo,
} from './services/videoBurnExportService'
import { runVideoSubtitle } from './services/videoSubtitleService'
import type { ExportFormat, ExportResult, WordExportMode } from './types/export'
import type { ImportResult } from './types/import'
import type { StartupCheckReport } from './types/environment'
import {
  type AsrModelSize,
  createDefaultAppConfig,
  createEmptyProjectState,
  type AppConfig,
  type OutputMode,
  type ProjectState,
  type ProviderName,
  type SubtitleSegment,
  type TranscriptionProviderName,
} from './types/models'
import type {
  AsrInputLanguage,
  AsrQualityPreset,
  TranscriptionDiagnostics,
} from './types/transcription'
import type {
  VideoSubtitleDraft,
  VideoSubtitleRunResponse,
} from './types/videoSubtitle'
import type {
  VideoBurnExportMode,
  VideoBurnExportResult,
} from './types/videoExport'
import type {
  SubtitleSummary,
  TaskEngineType,
  TaskHistoryRecord,
  TaskLogEntry,
  TaskLogLevel,
} from './types/tasks'
import {
  getTranslationConfigConsistencyIssue,
  hasUsableSpeechConfig,
  hasUsableTranslationConfig,
  isCloudSpeechProvider,
  isLocalSpeechProvider,
  safeTrim,
  selectProvider,
  updateDefaultTranscriptionProvider,
  updateActiveProviderModel,
  updateOutputMode,
} from './utils/config'

type WorkspaceKey =
  | 'import'
  | 'videoSubtitle'
  | 'translation'
  | 'preview'
  | 'aiWorkbench'
  | 'export'
  | 'settings'
type MainWorkspaceKey = Exclude<WorkspaceKey, 'settings'>

type TranslationRunMeta = {
  provider: ProviderName
  model: string
  baseUrl: string
} | null

type TranscriptionRunMeta = TranscriptionDiagnostics | null

type ExportRunMeta = ExportResult | null
type VideoBurnExportRunMeta = VideoBurnExportResult | null
type StartupCheckMeta = StartupCheckReport | null
type PreparedSegmentsResult = {
  segments: SubtitleSegment[]
  transcriptionRun: TranscriptionRunMeta
}

type WorkspaceCopy = {
  current: number
  title: string
  description: string
}

type LanguagePack = ReturnType<typeof useI18n>['m']
type StartTranslationOptions = {
  importResultOverride?: ImportResult
  projectStateOverride?: ProjectState
  taskOverride?: TaskHistoryRecord | null
}
type RestoreTaskTarget = 'translation' | 'preview' | 'export'
type AppNoticeTone = 'info' | 'warn'

function createEmptyAgentSessionState(): AgentSessionState {
  return {
    subtitleQuality: null,
    contentSummary: null,
  }
}

function createEmptyCommandAgentState(): CommandAgentState {
  return {
    items: [],
    activeItemId: undefined,
  }
}

function getVideoSubtitleSidebarCopy(
  language: ReturnType<typeof useI18n>['language'],
): {
  label: string
  description: string
} {
  return language === 'zh'
    ? {
        label: '视频字幕',
        description: '中文单语 / 英语双语',
      }
    : {
        label: 'Video subtitle',
        description: 'Chinese single / English bilingual',
      }
}

function getVideoSubtitleWorkspaceCopy(
  language: ReturnType<typeof useI18n>['language'],
): WorkspaceCopy {
  return language === 'zh'
    ? {
        current: 2,
        title: '生成视频字幕',
        description: '选一个视频，确认语言后开始生成字幕。',
      }
    : {
        current: 2,
        title: 'Generate video subtitles',
        description: 'Choose a video, confirm the language, then start subtitle generation.',
      }
}

function cloneSegments(segments: SubtitleSegment[]): SubtitleSegment[] {
  return segments.map((segment) => ({ ...segment }))
}

function getPathDirectory(path: string): string {
  const separatorIndex = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'))
  return separatorIndex >= 0 ? path.slice(0, separatorIndex) : ''
}

function getPathStem(path: string): string {
  const fileName = path.split(/[\\/]/).pop() || 'linguasub-video'
  return fileName.replace(/\.[^/.]+$/, '') || 'linguasub-video'
}

function buildDefaultBurnedVideoFileName(videoPath: string): string {
  return `${getPathStem(videoPath)}_subtitled.mp4`
}

function buildDefaultBurnedVideoOutputPath(videoPath: string): string {
  const directory = getPathDirectory(videoPath)
  const fileName = buildDefaultBurnedVideoFileName(videoPath)
  return directory ? `${directory}\\${fileName}` : fileName
}

function getCurrentVideoPath(
  importResult: ImportResult | null,
  projectState: ProjectState,
): string | null {
  if (importResult?.currentFile.mediaType === 'video') {
    return importResult.currentFile.path
  }

  if (projectState.currentFile?.mediaType === 'video') {
    return projectState.currentFile.path
  }

  return null
}

function getCurrentVideoName(
  importResult: ImportResult | null,
  projectState: ProjectState,
): string | null {
  if (importResult?.currentFile.mediaType === 'video') {
    return importResult.currentFile.name
  }

  if (projectState.currentFile?.mediaType === 'video') {
    return projectState.currentFile.name
  }

  return null
}

function cloneProjectState(projectState: ProjectState): ProjectState {
  return {
    currentFile: projectState.currentFile ? { ...projectState.currentFile } : null,
    segments: cloneSegments(projectState.segments),
    status: projectState.status,
    error: projectState.error,
  }
}

function cloneImportResult(importResult: ImportResult): ImportResult {
  return {
    currentFile: { ...importResult.currentFile },
    projectState: cloneProjectState(importResult.projectState),
    workflow: [...importResult.workflow],
    route: importResult.route,
    shouldSkipTranscription: importResult.shouldSkipTranscription,
    recognitionInput: importResult.recognitionInput
      ? { ...importResult.recognitionInput }
      : null,
    subtitleInput: importResult.subtitleInput ? { ...importResult.subtitleInput } : null,
  }
}

function getNowIso(): string {
  return new Date().toISOString()
}

function createTaskId(): string {
  return `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function buildTaskLogEntry(
  level: TaskLogLevel,
  message: string,
  details?: string | null,
): TaskLogEntry {
  const normalizedDetails = safeTrim(details)
  return {
    logId: `log-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: getNowIso(),
    level,
    message,
    details: normalizedDetails ? normalizedDetails : null,
  }
}

function buildSubtitleSummary(segments: SubtitleSegment[]): SubtitleSummary {
  return {
    segmentCount: segments.length,
    translatedCount: segments.filter((segment) => safeTrim(segment.translatedText)).length,
  }
}

function getTaskEngineType(
  importResult: ImportResult,
  transcriptionProvider: TranscriptionProviderName,
): TaskEngineType {
  if (importResult.route === 'translation') {
    return 'subtitleImport'
  }

  if (isCloudSpeechProvider(transcriptionProvider)) {
    return 'cloudTranscription'
  }

  return 'localTranscription'
}

function maskConfiguredSecret(value: string | null | undefined): string {
  return safeTrim(value) ? '已配置' : '未配置'
}

function getSpeechProviderLabel(provider: TranscriptionProviderName): string {
  switch (provider) {
    case 'baidu_realtime':
      return 'baidu_realtime'
    case 'baidu_file_async':
      return 'baidu_file_async'
    case 'tencent_realtime':
      return 'tencent_realtime'
    case 'tencent_file_async':
      return 'tencent_file_async'
    case 'xfyun_lfasr':
      return 'xfyun_lfasr'
    case 'xfyun_speed_transcription':
      return 'xfyun_speed_transcription'
    case 'openaiSpeech':
      return 'openaiSpeech'
    default:
      return 'localFasterWhisper'
  }
}

function getSpeechProviderEndpoint(config: AppConfig, provider: TranscriptionProviderName): string {
  switch (provider) {
    case 'baidu_realtime':
      return 'wss://vop.baidu.com/realtime_asr'
    case 'tencent_realtime':
      return safeTrim(config.tencentAppId)
        ? `wss://asr.cloud.tencent.com/asr/v2/${safeTrim(config.tencentAppId)}`
        : 'wss://asr.cloud.tencent.com/asr/v2/<appid>'
    case 'openaiSpeech':
      return safeTrim(config.speechBaseUrl) || '未配置'
    default:
      return '本地离线模式'
  }
}

function getSpeechProviderModel(config: AppConfig, provider: TranscriptionProviderName): string {
  switch (provider) {
    case 'baidu_realtime':
      return safeTrim(config.baiduDevPid) || '未配置'
    case 'tencent_realtime':
      return safeTrim(config.tencentEngineModelType) || '未配置'
    case 'openaiSpeech':
      return safeTrim(config.speechModel) || '未配置'
    default:
      return '本地 faster-whisper'
  }
}

function buildSpeechConfigLogDetails(
  config: AppConfig,
  provider: TranscriptionProviderName,
  modelSize: AsrModelSize,
  qualityPreset: AsrQualityPreset,
): string {
  if (provider === 'baidu_realtime') {
    return [
      `识别服务商：${getSpeechProviderLabel(provider)}`,
      `识别模型参数：dev_pid=${safeTrim(config.baiduDevPid) || '未配置'}`,
      `识别服务地址：${getSpeechProviderEndpoint(config, provider)}`,
      `百度 AppID：${maskConfiguredSecret(config.baiduAppId)}`,
      `百度 API Key：${maskConfiguredSecret(config.baiduApiKey)}`,
      `CUID：${safeTrim(config.baiduCuid) || '未配置'}`,
    ].join('\n')
  }

  if (provider === 'tencent_realtime') {
    return [
      `识别服务商：${getSpeechProviderLabel(provider)}`,
      `识别模型参数：engine_model_type=${safeTrim(config.tencentEngineModelType) || '未配置'}`,
      `识别服务地址：${getSpeechProviderEndpoint(config, provider)}`,
      `腾讯 AppID：${maskConfiguredSecret(config.tencentAppId)}`,
      `腾讯 SecretID：${maskConfiguredSecret(config.tencentSecretId)}`,
      `腾讯 SecretKey：${maskConfiguredSecret(config.tencentSecretKey)}`,
    ].join('\n')
  }

  if (provider === 'openaiSpeech') {
    return [
      `识别服务商：${getSpeechProviderLabel(provider)}`,
      `识别模型：${getSpeechProviderModel(config, provider)}`,
      `识别服务地址：${getSpeechProviderEndpoint(config, provider)}`,
      `识别 API Key：${maskConfiguredSecret(config.speechApiKey)}`,
    ].join('\n')
  }

  return [
    `识别服务商：${getSpeechProviderLabel(provider)}`,
    `识别模型：本地 faster-whisper / ${modelSize}`,
    `识别质量：${qualityPreset}`,
    '识别服务地址：本地离线模式',
    '识别 API Key：不需要',
  ].join('\n')
}

function buildTranslationConfigLogDetails(config: AppConfig): string {
  return [
    `翻译服务商：${config.defaultProvider}`,
    `翻译模型：${safeTrim(config.model) || '未配置'}`,
    `翻译服务地址：${safeTrim(config.baseUrl) || '未配置'}`,
    `翻译 API Key：${maskConfiguredSecret(config.apiKey)}`,
  ].join('\n')
}

function buildSpeechConfigUserHint(
  config: AppConfig,
  provider: TranscriptionProviderName,
  modelSize: AsrModelSize,
): string {
  if (isCloudSpeechProvider(provider)) {
    return `当前识别配置不完整。服务商：${getSpeechProviderLabel(provider)}；模型：${
      getSpeechProviderModel(config, provider)
    }；服务地址：${getSpeechProviderEndpoint(config, provider)}。请先到设置页补全这一识别 provider 需要的鉴权和模型参数。`
  }

  return `当前本地识别模式使用 faster-whisper（${modelSize}）。请先确认本地运行时和模型已就绪。`
}

function buildTranslationConfigUserHint(config: AppConfig): string {
  return `当前翻译配置不完整。服务商：${config.defaultProvider}；模型：${
    safeTrim(config.model) || '未配置'
  }；服务地址：${safeTrim(config.baseUrl) || '未配置'}。请先到设置页补全翻译 API Key、服务地址和模型。`
}

function getInitialProjectStateForRetry(task: TaskHistoryRecord): ProjectState {
  if (task.importSnapshot) {
    return cloneProjectState(task.importSnapshot.projectState)
  }

  if (task.projectSnapshot?.currentFile) {
    return {
      currentFile: { ...task.projectSnapshot.currentFile },
      segments: [],
      status: 'idle',
      error: null,
    }
  }

  return createEmptyProjectState()
}

function getFirstReadySpeechModelSize(
  startupCheck: StartupCheckReport | null,
): AsrModelSize | null {
  const firstReadyModel = startupCheck?.speechModels.find((model) => model.available)
  return firstReadyModel?.size ?? null
}

function areSegmentsEqual(
  currentSegments: SubtitleSegment[],
  savedSegments: SubtitleSegment[],
): boolean {
  if (currentSegments.length !== savedSegments.length) {
    return false
  }

  return currentSegments.every((segment, index) => {
    const savedSegment = savedSegments[index]
    return (
      segment.id === savedSegment.id &&
      segment.start === savedSegment.start &&
      segment.end === savedSegment.end &&
      segment.sourceText === savedSegment.sourceText &&
      segment.translatedText === savedSegment.translatedText &&
      segment.sourceLanguage === savedSegment.sourceLanguage &&
      segment.targetLanguage === savedSegment.targetLanguage
    )
  })
}

function formatSaveTime(date: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

function logExportDebugSummary(
  segments: SubtitleSegment[],
  format: ExportFormat,
  outputMode: OutputMode,
) {
  const firstSegment = segments[0] ?? null
  const lastSegment = segments[segments.length - 1] ?? null
  const maxEnd = segments.reduce(
    (currentMax, segment) =>
      Number.isFinite(segment.end) ? Math.max(currentMax, segment.end) : currentMax,
    Number.NEGATIVE_INFINITY,
  )

  console.info('[LinguaSub][ExportDebug][client]', {
    format,
    outputMode,
    segmentCount: segments.length,
    firstSegment: firstSegment
      ? {
          id: firstSegment.id,
          start: firstSegment.start,
          end: firstSegment.end,
        }
      : null,
    lastSegment: lastSegment
      ? {
          id: lastSegment.id,
          start: lastSegment.start,
          end: lastSegment.end,
        }
      : null,
    maxEnd: Number.isFinite(maxEnd) ? maxEnd : null,
    usesProjectStateSegments: true,
    previewFilteredSegmentsInvolved: false,
  })
}

function getOutputModeLabel(outputMode: OutputMode, m: LanguagePack): string {
  return m.common.outputModes[outputMode]
}

function getWordExportModeLabel(
  wordExportMode: WordExportMode,
  m: LanguagePack,
): string {
  return m.common.wordExportModes[wordExportMode]
}

function getExportFormatLabel(exportFormat: ExportFormat, m: LanguagePack): string {
  return m.common.exportFormats[exportFormat]
}

function getExportFileFormatValue(exportFormat: ExportFormat, m: LanguagePack): string {
  return m.exportPage.fileFormatValues[exportFormat]
}

function getExportStatusPoint(
  exportFormat: ExportFormat,
  outputMode: OutputMode,
  wordExportMode: WordExportMode,
  m: LanguagePack,
): string {
  if (exportFormat === 'word') {
    return `${m.exportPage.wordModeLabel}: ${getWordExportModeLabel(wordExportMode, m)}`
  }

  if (exportFormat === 'recognition_text') {
    return `${m.common.summary.exportFormat}: ${getExportFormatLabel(exportFormat, m)}`
  }

  if (exportFormat === 'content_summary_word') {
    return `${m.common.summary.exportFormat}: ${getExportFormatLabel(exportFormat, m)}`
  }

  return `${m.common.summary.outputMode}: ${getOutputModeLabel(outputMode, m)}`
}

function getTaskOutputFormat(
  exportFormat: ExportFormat,
  outputMode: OutputMode,
  wordExportMode: WordExportMode,
): string {
  if (exportFormat === 'word') {
    return `word:${wordExportMode}`
  }

  if (exportFormat === 'recognition_text') {
    return 'recognition_text'
  }

  if (exportFormat === 'content_summary_word') {
    return 'content_summary_word'
  }

  return outputMode === 'bilingual' ? 'srt:bilingual' : 'srt:single'
}

function getPrimaryExportActionLabel(
  exportFormat: ExportFormat,
  m: LanguagePack,
): string {
  if (exportFormat === 'word') {
    return m.common.buttons.exportWord
  }

  if (exportFormat === 'recognition_text') {
    return getExportFormatLabel(exportFormat, m)
  }

  if (exportFormat === 'content_summary_word') {
    return getExportFormatLabel(exportFormat, m)
  }

  return m.common.buttons.exportSrt
}

function getStatusLabel(status: ProjectState['status'], m: LanguagePack): string {
  return m.common.statuses[status]
}

function getProviderLabel(provider: ProviderName, m: LanguagePack): string {
  return m.common.providers[provider]
}

function getMediaTypeLabel(
  mediaType: ImportResult['currentFile']['mediaType'],
  m: LanguagePack,
): string {
  return m.importPage.mediaTypes[mediaType]
}

function getImportRouteLabel(importResult: ImportResult, m: LanguagePack): string {
  return importResult.route === 'recognition'
    ? m.app.routes.recognitionToTranslation
    : m.app.routes.srtParseToTranslation
}

function getWorkflowLabel(workflow: string[], m: LanguagePack): string {
  return workflow
    .map((step) => {
      const label = m.common.workflowSteps[step as keyof typeof m.common.workflowSteps]
      return label ?? step
    })
    .join(' -> ')
}

function getWorkspaceCopy(
  activeWorkspace: WorkspaceKey,
  language: ReturnType<typeof useI18n>['language'],
  m: LanguagePack,
): WorkspaceCopy {
  if (activeWorkspace === 'settings') {
    return {
      current: 7,
      title: m.app.workspace.settings.title,
      description: m.app.workspace.settings.description,
    }
  }

  if (activeWorkspace === 'videoSubtitle') {
    return getVideoSubtitleWorkspaceCopy(language)
  }

  if (activeWorkspace === 'translation') {
    return {
      current: 3,
      title: m.app.workspace.translation.title,
      description: m.app.workspace.translation.description,
    }
  }

  if (activeWorkspace === 'preview') {
    return {
      current: 4,
      title: m.app.workspace.preview.title,
      description: m.app.workspace.preview.description,
    }
  }

  if (activeWorkspace === 'aiWorkbench') {
    return {
      current: 5,
      title: m.app.workspace.aiWorkbench.title,
      description: m.app.workspace.aiWorkbench.description,
    }
  }

  if (activeWorkspace === 'export') {
    return {
      current: 6,
      title: m.app.workspace.export.title,
      description: m.app.workspace.export.description,
    }
  }

  return {
    current: 1,
    title: m.app.workspace.import.title,
    description: m.app.workspace.import.description,
  }
}

function buildHeaderMetrics(
  activeWorkspace: WorkspaceKey,
  importResult: ImportResult | null,
  projectState: ProjectState,
  outputMode: OutputMode,
  _exportFormat: ExportFormat,
  _wordExportMode: WordExportMode,
  config: AppConfig | null,
  translationRun: TranslationRunMeta,
  exportResult: ExportRunMeta,
  language: ReturnType<typeof useI18n>['language'],
  m: LanguagePack,
): HeaderMetric[] {
  if (activeWorkspace === 'videoSubtitle') {
    return language === 'zh'
      ? [
          {
            label: '模式',
            value: '中文单语',
            hint: '当前支持中文视频生成中文字幕。',
          },
          {
            label: '模式',
            value: '英语双语',
            hint: '当前支持英语视频生成中英字幕，英文 SRT 可选。',
          },
          {
            label: '翻译',
            value: config?.defaultProvider ?? m.common.misc.loading,
            hint: '英语双语会使用设置页里的翻译配置。',
          },
          {
            label: '完成后',
            value: '进入预览',
            hint: '生成完成后会自动进入预览页。',
          },
        ]
      : [
          {
            label: 'Mode',
            value: 'Chinese single',
            hint: 'Generate Chinese subtitles from Chinese videos.',
          },
          {
            label: 'Mode',
            value: 'English bilingual',
            hint: 'Generate bilingual subtitles from English videos. English SRT is optional.',
          },
          {
            label: 'Translation',
            value: config?.defaultProvider ?? m.common.misc.loading,
            hint: 'English bilingual output uses the translation setup from Settings.',
          },
          {
            label: 'After',
            value: 'Preview',
            hint: 'A successful run will jump to Preview automatically.',
          },
        ]
  }

  if (activeWorkspace === 'settings') {
    return [
      {
        label: m.common.language.label,
        value: language === 'zh' ? m.common.language.zh : m.common.language.en,
        hint: m.settingsPage.languageHint,
      },
      {
        label: m.common.summary.translationConfig,
        value: config ? getProviderLabel(config.defaultProvider, m) : m.common.misc.loading,
        hint: config
          ? hasUsableTranslationConfig(config)
            ? m.settingsPage.apiAvailable
            : m.settingsPage.apiMissing
          : m.app.labels.loadingTranslationConfig,
      },
      {
        label: m.common.buttons.uninstallLinguaSub,
        value: m.settingsPage.uninstallAvailability,
        hint: m.settingsPage.uninstallHelper,
      },
    ]
  }

  if (activeWorkspace === 'translation') {
    return [
      {
        label: m.common.misc.provider,
        value: config ? getProviderLabel(config.defaultProvider, m) : m.common.misc.loading,
        hint: config ? `${config.model} / ${getOutputModeLabel(outputMode, m)}` : m.app.labels.loadingTranslationConfig,
      },
      {
        label: m.common.summary.currentFile,
        value: importResult ? importResult.currentFile.name : m.common.misc.notSelected,
        hint: importResult ? getWorkflowLabel(importResult.workflow, m) : m.app.notes.translationNeedImport,
      },
      {
        label: m.common.misc.preparedSegments,
        value: String(projectState.segments.length),
        hint:
          projectState.segments.length > 0
            ? m.app.metrics.preparedSegmentsHint
            : m.app.metrics.preparedSegmentsPending,
      },
    ]
  }

  if (activeWorkspace === 'preview') {
    return [
      {
        label: m.common.summary.translatedSegments,
        value: String(projectState.segments.filter((segment) => segment.translatedText).length),
        hint: `${projectState.segments.length}`,
      },
      {
        label: m.common.summary.lastRun,
        value: translationRun?.provider ? getProviderLabel(translationRun.provider, m) : m.common.misc.notRecorded,
        hint: translationRun ? translationRun.model : m.common.misc.notRecorded,
      },
      {
        label: m.common.summary.outputMode,
        value: getOutputModeLabel(outputMode, m),
        hint: m.app.labels.previewOutputModeHint,
      },
    ]
  }

  if (activeWorkspace === 'aiWorkbench') {
    const translatedCount = projectState.segments.filter((segment) =>
      safeTrim(segment.translatedText),
    ).length
    const coverage =
      projectState.segments.length > 0
        ? Math.round((translatedCount / projectState.segments.length) * 100)
        : 0
    return [
      {
        label: m.aiWorkbench.subtitleCount,
        value: String(projectState.segments.length),
        hint:
          projectState.segments.length > 0
            ? m.aiWorkbench.contextDescription
            : m.aiWorkbench.emptyDescription,
      },
      {
        label: m.aiWorkbench.translatedCount,
        value: `${translatedCount} / ${projectState.segments.length}`,
        hint: m.aiWorkbench.translatedRate(coverage),
      },
      {
        label: m.aiWorkbench.videoName,
        value: getCurrentVideoName(importResult, projectState) ?? m.aiWorkbench.noVideo,
        hint: getCurrentVideoPath(importResult, projectState) ?? m.common.misc.notSelected,
      },
    ]
  }

  if (activeWorkspace === 'export') {
    const translatedCount = projectState.segments.filter((segment) => segment.translatedText).length
    return [
      {
        label: language === 'zh' ? '导出' : 'Export',
        value: 'SRT / TXT / Word / MP4',
        hint:
          language === 'zh'
            ? '导出页内选择具体类型后再生成文件。'
            : 'Choose the exact export type inside the Export page.',
      },
      {
        label: m.common.summary.subtitlePackage,
        value: String(projectState.segments.length),
        hint: `${m.common.summary.translatedRows}: ${translatedCount}`,
      },
      {
        label: m.common.summary.lastExport,
        value: exportResult?.fileName ?? m.common.misc.notExported,
        hint: exportResult ? exportResult.path : m.app.labels.exportPathHint,
      },
    ]
  }

  return [
    {
      label: language === 'zh' ? '输入' : 'Input',
      value: language === 'zh' ? '视频' : 'Video',
      hint: language === 'zh' ? '支持 MP4、MOV、MKV。' : 'MP4, MOV, and MKV are supported.',
    },
    {
      label: language === 'zh' ? '输入' : 'Input',
      value: language === 'zh' ? '音频' : 'Audio',
      hint: language === 'zh' ? '支持 MP3、WAV、M4A。' : 'MP3, WAV, and M4A are supported.',
    },
    {
      label: language === 'zh' ? '输入' : 'Input',
      value: 'SRT',
      hint: language === 'zh' ? '支持 SRT 字幕文件。' : 'SRT subtitle files are supported.',
    },
    {
      label: language === 'zh' ? '文件' : 'File',
      value: importResult ? importResult.currentFile.name : m.common.misc.notSelected,
      hint: importResult ? importResult.currentFile.path : m.app.notes.importNeedFile,
    },
    {
      label: language === 'zh' ? '下一步' : 'Next',
      value: importResult
        ? importResult.route === 'recognition'
          ? language === 'zh'
            ? '识别 / 翻译'
            : 'Recognition / Translation'
          : language === 'zh'
            ? 'SRT 翻译'
            : 'SRT Translation'
        : language === 'zh'
          ? '自动判断流程'
          : 'Auto route',
      hint: importResult
        ? getWorkflowLabel(importResult.workflow, m)
        : m.importPage.workflowWaitingDescription,
    },
  ]
}

function buildSidebarStatus(
  activeWorkspace: WorkspaceKey,
  importResult: ImportResult | null,
  projectState: ProjectState,
  importError: string | null,
  configError: string | null,
  processError: string | null,
  uninstallError: string | null,
  isUninstalling: boolean,
  isWorking: boolean,
  outputMode: OutputMode,
  exportFormat: ExportFormat,
  wordExportMode: WordExportMode,
  exportResult: ExportRunMeta,
  language: ReturnType<typeof useI18n>['language'],
  m: LanguagePack,
): SidebarStatus {
  if (activeWorkspace === 'settings') {
    if (uninstallError) {
      return {
        label: m.common.statuses.error,
        hint: uninstallError,
        points: [
          m.settingsPage.uninstallWarningDescription,
          m.settingsPage.uninstallHelper,
          m.common.buttons.reloadConfig,
        ],
      }
    }

    if (configError) {
      return {
        label: m.common.statuses.error,
        hint: configError,
        points: [
          m.app.errors.configLoadFailed,
          m.common.buttons.reloadConfig,
          m.common.summary.configPath,
        ],
      }
    }

    if (isUninstalling) {
      return {
        label: m.common.buttons.uninstalling,
        hint: m.settingsPage.uninstallingHint,
        points: [
          m.settingsPage.uninstallWarningDescription,
          m.settingsPage.uninstallHelper,
          m.settingsPage.uninstallCloseReminder,
        ],
      }
    }

    return {
      label: m.common.statuses.idle,
      hint: m.app.hints.settingsReady,
      points: [
        m.settingsPage.languageHint,
        m.settingsPage.uninstallWarningDescription,
        m.settingsPage.uninstallHelper,
      ],
    }
  }

  if (activeWorkspace === 'videoSubtitle') {
    if (configError) {
      return {
        label: m.common.statuses.error,
        hint: configError,
        points: [
          m.app.errors.configLoadFailed,
          m.common.buttons.reloadConfig,
          m.common.summary.configPath,
        ],
      }
    }

    if (processError) {
      return language === 'zh'
        ? {
            label: m.common.statuses.error,
            hint: processError,
            points: [
              '当前阶段只支持 中文 + 单语，或 英语 + 双语。',
              '请先检查视频路径、媒体环境，以及当前识别/翻译配置。',
              '需要时先打开设置页补全相关 provider 参数。',
            ],
          }
        : {
            label: m.common.statuses.error,
            hint: processError,
            points: [
              'This phase only supports Chinese + single-language output, or English + bilingual output.',
              'Check the video path, media runtime, and the current speech / translation config.',
              'Open Settings first if any provider still needs work.',
            ],
          }
    }

    if (isWorking) {
      return language === 'zh'
        ? {
            label: m.common.statuses.transcribing,
            hint: '正在处理视频字幕任务。',
            points: [
              '中文单语：只调用现有 transcribe_media()。',
              '英语双语：先识别，再调用现有 translate_segments()。',
              '成功后会直接进入预览页。',
            ],
          }
        : {
            label: m.common.statuses.transcribing,
            hint: 'Processing the video subtitle task.',
            points: [
              'Chinese single-language: transcribe_media() only.',
              'English bilingual: transcribe first, then reuse translate_segments().',
              'A successful run will jump straight to Preview.',
            ],
          }
    }

    return language === 'zh'
      ? {
          label: m.common.statuses.idle,
          hint: '选择视频后即可开始当前阶段的两条最小链路。',
          points: [
            '输入项只保留视频路径、源语言和输出模式。',
            '当前只开放 中文 + 单语，或 英语 + 双语。',
            '结果会继续复用现有 Preview / Export。',
          ],
        }
      : {
          label: m.common.statuses.idle,
          hint: 'Choose a video file to start one of the MVP paths.',
          points: [
            'The page only keeps video path, source language, and output mode.',
            'Only Chinese + single-language output, or English + bilingual output, is enabled.',
            'The result will continue into the existing Preview / Export flow.',
          ],
        }
  }

  if (processError) {
    return {
      label: m.common.statuses.error,
      hint: processError,
      points: [
        m.app.notes.importNeedFile,
        m.importPage.environment.warnings.ffmpeg,
        m.exportPage.missingLinesDescription(1),
      ],
    }
  }

  if (configError) {
    return {
      label: m.common.statuses.error,
      hint: configError,
      points: [
        m.app.errors.configLoadFailed,
        m.common.buttons.reloadConfig,
        m.common.summary.configPath,
      ],
    }
  }

  if (importError) {
    return {
      label: m.common.statuses.idle,
      hint: importError,
      points: [
        m.importPage.pathTitle,
        m.app.labels.supportedInputHint,
        m.common.buttons.importFile,
      ],
    }
  }

  if (activeWorkspace === 'export' && projectState.segments.length === 0) {
    return {
      label: m.common.statuses.idle,
      hint: m.exportPage.noSubtitleDescription,
      points: [
        m.app.notes.previewReady,
        m.common.summary.livePreviewEdits,
        getExportStatusPoint(exportFormat, outputMode, wordExportMode, m),
      ],
    }
  }

  if (activeWorkspace === 'export' && projectState.status === 'done' && exportResult) {
    return {
      label: m.common.statuses.done,
      hint: m.exportPage.lastExportDescription(exportResult.fileName),
      points: [
        `${m.common.summary.exportFormat}: ${getExportFileFormatValue(exportResult.format, m)}`,
        `${m.common.summary.subtitleRows}: ${exportResult.count}`,
        `${m.common.summary.path}: ${exportResult.path}`,
      ],
    }
  }

  if (activeWorkspace === 'export') {
    return {
      label: getStatusLabel(projectState.status, m),
      hint:
        projectState.status === 'exporting'
          ? m.app.hints.exportWriting
          : m.app.hints.exportReady,
      points: [
        `${m.common.summary.currentFile}: ${importResult?.currentFile.name ?? m.common.misc.notSelected}`,
        `${m.common.misc.preparedSegments}: ${projectState.segments.length}`,
        getExportStatusPoint(exportFormat, outputMode, wordExportMode, m),
      ],
    }
  }

  if (activeWorkspace === 'aiWorkbench') {
    const translatedCount = projectState.segments.filter((segment) =>
      safeTrim(segment.translatedText),
    ).length
    return {
      label: getStatusLabel(projectState.status, m),
      hint:
        projectState.segments.length > 0
          ? m.aiWorkbench.contextDescription
          : m.aiWorkbench.emptyDescription,
      points: [
        `${m.aiWorkbench.subtitleCount}: ${projectState.segments.length}`,
        `${m.aiWorkbench.translatedCount}: ${translatedCount}`,
        m.aiWorkbench.commandInputComingSoon,
      ],
    }
  }

  if (!importResult) {
    return {
      label: m.common.statuses.idle,
      hint: m.importPage.workflowWaitingDescription,
      points: [
        m.importPage.workflowExamples[0].description,
        m.importPage.workflowExamples[1].description,
        m.importPage.sections.backend.description,
      ],
    }
  }

  if (projectState.status === 'done') {
    if (isVideoSubtitleImportResult(importResult)) {
      return language === 'zh'
        ? {
            label: m.common.statuses.done,
            hint:
              outputMode === 'bilingual'
                ? '识别与翻译完成，已生成中英字幕。'
                : '识别完成，已生成中文字幕。',
            points: [
              `${m.common.summary.translatedSegments}: ${projectState.segments.filter((segment) => segment.translatedText).length}`,
              `${m.common.summary.outputMode}: ${getOutputModeLabel(outputMode, m)}`,
              m.common.buttons.openExport,
            ],
          }
        : {
            label: m.common.statuses.done,
            hint:
              outputMode === 'bilingual'
                ? 'Recognition and translation finished. Bilingual subtitles are ready.'
                : 'Recognition finished. Chinese subtitles are ready.',
            points: [
              `${m.common.summary.translatedSegments}: ${projectState.segments.filter((segment) => segment.translatedText).length}`,
              `${m.common.summary.outputMode}: ${getOutputModeLabel(outputMode, m)}`,
              m.common.buttons.openExport,
            ],
          }
    }

    return {
      label: m.common.statuses.done,
      hint: m.app.notes.previewReady,
      points: [
        `${m.common.summary.translatedSegments}: ${projectState.segments.filter((segment) => segment.translatedText).length}`,
        `${m.common.summary.outputMode}: ${getOutputModeLabel(outputMode, m)}`,
        m.common.buttons.openExport,
      ],
    }
  }

  return {
    label: getStatusLabel(projectState.status, m),
    hint:
      projectState.status === 'transcribing'
        ? `${importResult.currentFile.name} · ${m.common.statuses.transcribing}`
        : `${importResult.currentFile.name} · ${m.common.statuses.translating}`,
    points: [
      `${m.common.summary.type}: ${getMediaTypeLabel(importResult.currentFile.mediaType, m)}`,
      `${m.common.misc.preparedSegments}: ${projectState.segments.length}`,
      `${m.common.summary.outputMode}: ${getOutputModeLabel(outputMode, m)}`,
      `${m.common.summary.route}: ${getWorkflowLabel(importResult.workflow, m)}`,
    ],
  }
}

function buildSidebarItems(
  activeWorkspace: WorkspaceKey,
  importResult: ImportResult | null,
  projectState: ProjectState,
  isBusy: boolean,
  language: ReturnType<typeof useI18n>['language'],
  m: LanguagePack,
) {
  const activeKey =
    activeWorkspace === 'settings'
      ? 'settings'
      : activeWorkspace === 'videoSubtitle'
      ? 'videoSubtitle'
      : activeWorkspace === 'export'
      ? 'export'
      : activeWorkspace === 'aiWorkbench'
      ? 'aiWorkbench'
      : activeWorkspace === 'preview'
        ? 'preview'
        : activeWorkspace === 'translation' &&
            isBusy &&
            projectState.status === 'transcribing' &&
            importResult?.route === 'recognition'
          ? 'recognition'
          : activeWorkspace === 'translation'
            ? 'translation'
            : 'import'

  const hasImport = Boolean(importResult)
  const hasSegments = projectState.segments.length > 0
  const videoSubtitleProject = isVideoSubtitleImportResult(importResult)

  return sidebarItemKeys.map((key) => ({
    key,
    label:
      key === 'videoSubtitle'
        ? getVideoSubtitleSidebarCopy(language).label
        : m.sidebar.items[key].label,
    description:
      key === 'videoSubtitle'
        ? getVideoSubtitleSidebarCopy(language).description
        : m.sidebar.items[key].description,
    active: key === activeKey,
    disabled:
      key === 'settings'
        ? isBusy
        : key === 'videoSubtitle'
          ? isBusy
        : key === 'translation' || key === 'recognition'
          ? isBusy || !hasImport || videoSubtitleProject
          : key === 'preview' || key === 'export'
            ? isBusy || !hasSegments
            : key === 'aiWorkbench'
              ? isBusy
            : isBusy,
  }))
}

function buildStatusHint(
  activeWorkspace: WorkspaceKey,
  importResult: ImportResult | null,
  projectState: ProjectState,
  importError: string | null,
  configError: string | null,
  processError: string | null,
  uninstallError: string | null,
  isUninstalling: boolean,
  isWorking: boolean,
  outputMode: OutputMode,
  exportResult: ExportRunMeta,
  language: ReturnType<typeof useI18n>['language'],
  m: LanguagePack,
): string {
  if (activeWorkspace === 'settings') {
    if (uninstallError) {
      return uninstallError
    }

    if (configError) {
      return configError
    }

    return isUninstalling ? m.settingsPage.uninstallingHint : m.app.hints.settingsReady
  }

  if (activeWorkspace === 'videoSubtitle') {
    if (processError) {
      return processError
    }

    if (configError) {
      return configError
    }

    if (isWorking) {
      return language === 'zh'
        ? '正在处理视频字幕任务。'
        : 'Processing the video subtitle task.'
    }

    return language === 'zh'
      ? '这一页当前支持 中文 + 单语，或 英语 + 双语。'
      : 'This page currently supports Chinese + single-language output, or English + bilingual output.'
  }

  if (processError) {
    return processError
  }

  if (configError) {
    return configError
  }

  if (importError) {
    return importError
  }

  if (!importResult) {
    return m.app.hints.importDefault
  }

  if (activeWorkspace === 'export') {
    if (projectState.status === 'exporting') {
      return m.app.hints.exportWriting
    }

    if (exportResult && projectState.status === 'done') {
      return m.exportPage.lastExportDescription(exportResult.fileName)
    }

    return m.app.hints.exportReady
  }

  if (activeWorkspace === 'aiWorkbench') {
    return projectState.segments.length > 0
      ? m.aiWorkbench.contextDescription
      : m.aiWorkbench.emptyDescription
  }

  if (projectState.status === 'done') {
    if (isVideoSubtitleImportResult(importResult)) {
      if (outputMode === 'bilingual') {
        return language === 'zh'
          ? '识别与翻译完成，已生成中英字幕。'
          : 'Recognition and translation finished. Bilingual subtitles are ready.'
      }

      return language === 'zh'
        ? '识别完成，已生成中文字幕。'
        : 'Recognition finished. Chinese subtitles are ready.'
    }

    return m.app.hints.translationDone
  }

  return `${importResult.currentFile.name} · ${m.common.summary.route}: ${getImportRouteLabel(importResult, m)}`
}

function buildActionBarNote(
  activeWorkspace: WorkspaceKey,
  importResult: ImportResult | null,
  m: LanguagePack,
): string {
  if (activeWorkspace === 'videoSubtitle') {
    return '当前阶段支持两条链路：中文视频 -> 中文字幕，或 英语视频 -> 中英字幕。成功后都会直接进入预览页。'
  }

  if (activeWorkspace === 'settings') {
    return m.app.notes.settingsReady
  }

  if (activeWorkspace === 'translation') {
    if (!importResult) {
      return m.app.notes.translationNeedImport
    }

    return importResult.route === 'recognition'
      ? m.app.notes.translationRecognition
      : m.app.notes.translationSrt
  }

  if (activeWorkspace === 'preview') {
    return m.app.notes.previewReady
  }

  if (activeWorkspace === 'export') {
    return m.app.notes.exportReady
  }

  if (!importResult) {
    return m.app.notes.importNeedFile
  }

  return importResult.shouldSkipTranscription
    ? m.app.notes.srtImported
    : m.app.notes.mediaImported
}

function getWorkspaceFromSidebarKey(key: SidebarItemKey): WorkspaceKey {
  if (key === 'recognition' || key === 'translation') {
    return 'translation'
  }

  return key
}

function isWorkspaceKey(value: string): value is WorkspaceKey {
  return (
    value === 'import' ||
    value === 'videoSubtitle' ||
    value === 'translation' ||
    value === 'preview' ||
    value === 'aiWorkbench' ||
    value === 'export' ||
    value === 'settings'
  )
}

function getStartupLoadingNotice(language: ReturnType<typeof useI18n>['language']): {
  title: string
  description: string
  tone: AppNoticeTone
} {
  return language === 'zh'
    ? {
        title: '正在启动 LinguaSub...',
        description: '正在读取配置、环境状态和最近任务。即使部分数据稍后加载失败，你仍可继续导入文件。',
        tone: 'info',
      }
    : {
        title: 'Starting LinguaSub...',
        description:
          'LinguaSub is loading your config, environment checks, and recent tasks. You can still keep working even if part of startup data fails later.',
        tone: 'info',
      }
}

function getStartupRecoveryNotice(language: ReturnType<typeof useI18n>['language']): {
  title: string
  description: string
  tone: AppNoticeTone
} {
  return language === 'zh'
    ? {
        title: '启动时部分数据加载失败',
        description:
          '已自动进入首页，你仍可继续导入文件。最近任务、配置或环境检查如果稍后恢复正常，界面会继续可用。',
        tone: 'warn',
      }
    : {
        title: 'Part of startup data failed to load',
        description:
          'LinguaSub already returned to the home page. You can keep importing files while config, recent tasks, or environment checks recover later.',
        tone: 'warn',
      }
}

function getWorkspaceRecoveryNotice(language: ReturnType<typeof useI18n>['language']): {
  title: string
  description: string
  tone: AppNoticeTone
} {
  return language === 'zh'
    ? {
        title: '页面状态异常，已返回首页',
        description: '检测到无效页面状态，LinguaSub 已自动回到首页，主流程仍可继续使用。',
        tone: 'warn',
      }
    : {
        title: 'Recovered from an invalid page state',
        description:
          'LinguaSub detected an unexpected workspace state and safely returned to the home page.',
        tone: 'warn',
      }
}

async function prepareSegmentsForTranslation(
  importResult: ImportResult,
  existingSegments: SubtitleSegment[],
  setProjectState: Dispatch<SetStateAction<ProjectState>>,
  m: LanguagePack,
  config: AppConfig,
  transcriptionProvider: TranscriptionProviderName,
  asrModelSize: AsrModelSize,
  asrLanguage: AsrInputLanguage,
  asrQualityPreset: AsrQualityPreset,
): Promise<PreparedSegmentsResult> {
  if (existingSegments.length > 0) {
    return {
      segments: existingSegments,
      transcriptionRun: null,
    }
  }

  if (importResult.route === 'translation') {
    const subtitlePath = importResult.subtitleInput?.subtitlePath
    if (!subtitlePath) {
      throw new Error(m.app.errors.missingSubtitleParsePath)
    }

    startTransition(() => {
      setProjectState((current) => ({
        ...current,
        status: 'translating',
        error: null,
      }))
    })

    const parseResult = await parseSrt(subtitlePath)
    startTransition(() => {
      setProjectState((current) => ({
        ...current,
        segments: parseResult.segments,
        status: 'translating',
        error: null,
      }))
    })
    return {
      segments: parseResult.segments,
      transcriptionRun: null,
    }
  }

  const mediaPath = importResult.recognitionInput?.mediaPath
  if (!mediaPath) {
    throw new Error(m.app.errors.missingRecognitionPath)
  }

  startTransition(() => {
    setProjectState((current) => ({
      ...current,
      status: 'transcribing',
      error: null,
    }))
  })

  const recognitionResult = await transcribeMedia(
    mediaPath,
    {
      provider: transcriptionProvider,
      language: asrLanguage,
      modelSize: asrModelSize,
      qualityPreset: asrQualityPreset,
      config,
    },
  )
  startTransition(() => {
    setProjectState((current) => ({
      ...current,
      segments: recognitionResult.segments,
      status: 'translating',
      error: null,
    }))
  })
  return {
    segments: recognitionResult.segments,
    transcriptionRun: recognitionResult.diagnostics,
  }
}

function buildVideoSubtitleImportResult(
  response: VideoSubtitleRunResponse,
  subtitlePath: string | null = null,
): ImportResult {
  return {
    currentFile: { ...response.currentFile },
    projectState: {
      currentFile: { ...response.currentFile },
      segments: cloneSegments(response.segments),
      status: 'done',
      error: null,
    },
    workflow: ['Video', 'Recognition', 'Export'],
    route: 'recognition',
    shouldSkipTranscription: false,
    recognitionInput: {
      mediaPath: response.currentFile.path,
      mediaType: 'video',
      sourceLanguage: response.sourceLanguage,
    },
    subtitleInput: subtitlePath
      ? {
          subtitlePath,
          parser: 'srt',
          encoding: 'auto',
        }
      : null,
  }
}

function isVideoSubtitleImportResult(importResult: ImportResult | null): boolean {
  if (!importResult) {
    return false
  }

  return (
    importResult.route === 'recognition' &&
    importResult.workflow.length === 3 &&
    importResult.workflow[0] === 'Video' &&
    importResult.workflow[1] === 'Recognition' &&
    importResult.workflow[2] === 'Export'
  )
}

function App() {
  const { m, language } = useI18n()
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceKey>('import')
  const [lastMainWorkspace, setLastMainWorkspace] = useState<MainWorkspaceKey>('import')
  const [projectState, setProjectState] = useState(createEmptyProjectState())
  const [agentState, setAgentState] = useState<AgentSessionState>(
    createEmptyAgentSessionState,
  )
  const [commandAgentState, setCommandAgentState] = useState<CommandAgentState>(
    createEmptyCommandAgentState,
  )
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [processError, setProcessError] = useState<string | null>(null)
  const [isConfigLoading, setIsConfigLoading] = useState(true)
  const [isWorking, setIsWorking] = useState(false)
  const [transcriptionRun, setTranscriptionRun] = useState<TranscriptionRunMeta>(null)
  const [translationRun, setTranslationRun] = useState<TranslationRunMeta>(null)
  const [exportResult, setExportResult] = useState<ExportRunMeta>(null)
  const [videoBurnExportResult, setVideoBurnExportResult] =
    useState<VideoBurnExportRunMeta>(null)
  const [videoBurnMode, setVideoBurnMode] = useState<VideoBurnExportMode>('bilingual')
  const [isVideoBurnExporting, setIsVideoBurnExporting] = useState(false)
  const [startupCheck, setStartupCheck] = useState<StartupCheckMeta>(null)
  const [startupCheckError, setStartupCheckError] = useState<string | null>(null)
  const [isStartupCheckLoading, setIsStartupCheckLoading] = useState(true)
  const [isBootstrapping, setIsBootstrapping] = useState(true)
  const [hasStartupRecovery, setHasStartupRecovery] = useState(false)
  const [taskHistory, setTaskHistory] = useState<TaskHistoryRecord[]>([])
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [isHistoryLoading, setIsHistoryLoading] = useState(true)
  const [currentTask, setCurrentTask] = useState<TaskHistoryRecord | null>(null)
  const [selectedAsrModelSize, setSelectedAsrModelSize] = useState<AsrModelSize>('small')
  const [selectedAsrLanguage, setSelectedAsrLanguage] = useState<AsrInputLanguage>('auto')
  const [selectedAsrQualityPreset, setSelectedAsrQualityPreset] =
    useState<AsrQualityPreset>('balanced')
  const [isModelDownloadStarting, setIsModelDownloadStarting] = useState(false)
  const [videoSubtitleDraft, setVideoSubtitleDraft] = useState<VideoSubtitleDraft>({
    videoPath: '',
    subtitlePath: '',
    sourceLanguage: 'zh',
    outputMode: 'single',
  })
  const [fallbackOutputMode, setFallbackOutputMode] = useState<OutputMode>('bilingual')
  const [selectedExportFormat, setSelectedExportFormat] = useState<ExportFormat>('srt')
  const [selectedWordExportMode, setSelectedWordExportMode] =
    useState<WordExportMode>('bilingualTable')
  const [exportFileName, setExportFileName] = useState('')
  const [savedSegmentsSnapshot, setSavedSegmentsSnapshot] = useState<SubtitleSegment[]>([])
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null)
  const [isUninstalling, setIsUninstalling] = useState(false)
  const [uninstallError, setUninstallError] = useState<string | null>(null)
  const currentTaskRef = useRef<TaskHistoryRecord | null>(null)

  const hydrateConfig = useCallback(async (): Promise<boolean> => {
    setIsConfigLoading(true)

    try {
      const result = await loadConfig()
      startTransition(() => {
        setConfig(result)
        setFallbackOutputMode(result.outputMode)
        setConfigError(null)
      })
      return true
    } catch (error) {
      console.error('LinguaSub failed to load config during startup.', error)
      const message =
        error instanceof Error ? error.message : m.app.errors.configLoadFailed
      startTransition(() => {
        setConfigError(message)
      })
      return false
    } finally {
      setIsConfigLoading(false)
    }
  }, [m.app.errors.configLoadFailed])

  const hydrateStartupCheck = useCallback(async (): Promise<boolean> => {
    setIsStartupCheckLoading(true)

    try {
      const report = await loadEnvironmentCheck()
      startTransition(() => {
        setStartupCheck(report)
        setStartupCheckError(null)
      })
      return true
    } catch (error) {
      console.error('LinguaSub failed to load startup checks.', error)
      const message =
        error instanceof Error ? error.message : m.app.errors.startupCheckFailed
      startTransition(() => {
        setStartupCheckError(message)
      })
      return false
    } finally {
      setIsStartupCheckLoading(false)
    }
  }, [m.app.errors.startupCheckFailed])

  const hydrateTaskHistory = useCallback(async (): Promise<boolean> => {
    setIsHistoryLoading(true)

    try {
      const tasks = await loadTaskHistory()
      startTransition(() => {
        setTaskHistory(tasks)
        setHistoryError(null)
      })
      return true
    } catch (error) {
      console.error('LinguaSub failed to load recent tasks.', error)
      const message =
        error instanceof Error ? error.message : '无法读取最近任务，请稍后重试。'
      startTransition(() => {
        setTaskHistory([])
        setHistoryError(message)
      })
      return false
    } finally {
      setIsHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    let isDisposed = false

    async function bootstrapApp() {
      setIsBootstrapping(true)

      try {
        const results = await Promise.allSettled([
          hydrateConfig(),
          hydrateStartupCheck(),
          hydrateTaskHistory(),
        ])

        const [configResult, startupResult, historyResult] = results
        const configReady =
          configResult.status === 'fulfilled' ? configResult.value : false
        const startupReady =
          startupResult.status === 'fulfilled' ? startupResult.value : false
        const historyReady =
          historyResult.status === 'fulfilled' ? historyResult.value : false

        if (configResult.status === 'rejected') {
          console.error(
            'LinguaSub bootstrap saw an unexpected config bootstrap rejection.',
            configResult.reason,
          )
        }

        if (startupResult.status === 'rejected') {
          console.error(
            'LinguaSub bootstrap saw an unexpected startup-check rejection.',
            startupResult.reason,
          )
        }

        if (historyResult.status === 'rejected') {
          console.error(
            'LinguaSub bootstrap saw an unexpected history bootstrap rejection.',
            historyResult.reason,
          )
        }

        if (isDisposed) {
          return
        }

        const degradedStartup = !configReady || !startupReady || !historyReady
        startTransition(() => {
          setHasStartupRecovery(degradedStartup)
          if (degradedStartup) {
            setActiveWorkspace('import')
            setLastMainWorkspace('import')
          }
        })
      } catch (error) {
        console.error('LinguaSub bootstrap failed unexpectedly.', error)

        if (isDisposed) {
          return
        }

        startTransition(() => {
          setHasStartupRecovery(true)
          setActiveWorkspace('import')
          setLastMainWorkspace('import')
        })
      } finally {
        if (!isDisposed) {
          setIsBootstrapping(false)
        }
      }
    }

    void bootstrapApp()

    return () => {
      isDisposed = true
    }
  }, [hydrateConfig, hydrateStartupCheck, hydrateTaskHistory])

  useEffect(() => {
    currentTaskRef.current = currentTask
  }, [currentTask])

  const resolvedWorkspace = isWorkspaceKey(activeWorkspace) ? activeWorkspace : 'import'

  useEffect(() => {
    if (resolvedWorkspace === activeWorkspace) {
      return
    }

    console.error('LinguaSub recovered an invalid workspace state.', activeWorkspace)
    startTransition(() => {
      setActiveWorkspace('import')
      setLastMainWorkspace('import')
    })
  }, [activeWorkspace, resolvedWorkspace])

  const persistTaskRecord = useCallback(async (record: TaskHistoryRecord) => {
    try {
      const savedRecord = await upsertTaskHistoryRecord(record)
      startTransition(() => {
        setCurrentTask(savedRecord)
        setTaskHistory((current) => [
          savedRecord,
          ...current.filter((item) => item.taskId !== savedRecord.taskId),
        ])
        setHistoryError(null)
      })

      return savedRecord
    } catch (error) {
      console.error('LinguaSub failed to persist task history.', error)
      startTransition(() => {
        setCurrentTask(record)
        setTaskHistory((current) => [
          record,
          ...current.filter((item) => item.taskId !== record.taskId),
        ])
        setHistoryError('最近任务暂时无法写入本地，但当前导入和处理仍可继续。')
      })

      return record
    }
  }, [])

  const patchCurrentTask = useCallback(
    async (
      patch: Partial<TaskHistoryRecord>,
      appendLogs: TaskLogEntry[] = [],
      taskOverride?: TaskHistoryRecord | null,
    ) => {
      const baseTask = taskOverride ?? currentTaskRef.current
      if (!baseTask) {
        return null
      }

      const nextTask: TaskHistoryRecord = {
        ...baseTask,
        ...patch,
        outputFormats: patch.outputFormats ?? baseTask.outputFormats,
        exportPaths: patch.exportPaths ?? baseTask.exportPaths,
        logs: patch.logs ?? [...baseTask.logs, ...appendLogs],
        updatedAt: getNowIso(),
      }

      return persistTaskRecord(nextTask)
    },
    [persistTaskRecord],
  )

  function createTaskRecordFromImport(result: ImportResult): TaskHistoryRecord {
    const now = getNowIso()
    const transcriptionProvider =
      result.route === 'recognition'
        ? config?.defaultTranscriptionProvider ?? 'baidu_realtime'
        : null

    return {
      taskId: createTaskId(),
      sourceFilePath: result.currentFile.path,
      sourceFileName: result.currentFile.name,
      taskMode:
        result.route === 'recognition' ? 'extractAndTranslate' : 'translateSubtitle',
      sourceLanguage:
        result.route === 'recognition'
          ? selectedAsrLanguage
          : result.projectState.segments[0]?.sourceLanguage ?? 'auto',
      targetLanguage: 'zh-CN',
      outputFormats: [],
      engineType: transcriptionProvider
        ? getTaskEngineType(result, transcriptionProvider)
        : 'subtitleImport',
      status: 'queued',
      createdAt: now,
      updatedAt: now,
      exportPaths: [],
      errorMessage: null,
      subtitleSummary: buildSubtitleSummary(result.projectState.segments),
      importSnapshot: cloneImportResult(result),
      projectSnapshot: cloneProjectState(result.projectState),
      logs: [
        buildTaskLogEntry(
          'info',
          result.currentFile.requiresAsr
            ? '已导入媒体文件，下一步可以开始字幕提取和翻译。'
            : '已导入字幕文件，可以直接进入翻译流程。',
          `文件：${result.currentFile.path}\n流程：${getWorkflowLabel(result.workflow, m)}`,
        ),
      ],
      transcriptionProvider,
      transcriptionModelSize:
        transcriptionProvider && isLocalSpeechProvider(transcriptionProvider)
          ? selectedAsrModelSize
          : null,
      transcriptionQualityPreset:
        transcriptionProvider && isLocalSpeechProvider(transcriptionProvider)
          ? selectedAsrQualityPreset
          : null,
      translationProvider: config?.defaultProvider ?? null,
      translationModel: config?.model ?? null,
      outputMode: config?.outputMode ?? fallbackOutputMode,
    }
  }

  function restoreTaskState(
    task: TaskHistoryRecord,
    target: RestoreTaskTarget,
    options?: {
      projectStateOverride?: ProjectState
      processErrorOverride?: string | null
    },
  ) {
    if (!task.importSnapshot && !task.projectSnapshot) {
      setHistoryError('该历史任务缺少可恢复的数据，请重新导入源文件。')
      return
    }

    const restoredImport = task.importSnapshot ? cloneImportResult(task.importSnapshot) : null
    const restoredProject = options?.projectStateOverride
      ? cloneProjectState(options.projectStateOverride)
      : task.projectSnapshot
        ? cloneProjectState(task.projectSnapshot)
        : restoredImport
          ? cloneProjectState(restoredImport.projectState)
          : createEmptyProjectState()

    startTransition(() => {
      setCurrentTask(task)
      setImportResult(restoredImport)
      setProjectState(restoredProject)
      setAgentState(createEmptyAgentSessionState())
      setImportError(null)
      setProcessError(options?.processErrorOverride ?? null)
      setExportResult(null)
      setVideoBurnExportResult(null)
      setExportFileName('')
      setSavedSegmentsSnapshot(cloneSegments(restoredProject.segments))
      setLastSavedAt(task.updatedAt ? formatSaveTime(new Date(task.updatedAt)) : null)
      setTranslationRun(
        task.translationProvider && task.translationModel
          ? {
              provider: task.translationProvider as ProviderName,
              model: task.translationModel,
              baseUrl: config?.baseUrl ?? '',
            }
          : null,
      )
      setActiveWorkspace(target)
      setLastMainWorkspace(target === 'export' ? 'preview' : target)
      setHistoryError(null)
    })
  }

  useEffect(() => {
    const firstReadyModel = getFirstReadySpeechModelSize(startupCheck)
    if (!firstReadyModel) {
      return
    }

    const selectedModelReady = startupCheck?.speechModels.some(
      (model) => model.size === selectedAsrModelSize && model.available,
    )
    if (!selectedModelReady) {
      setSelectedAsrModelSize(firstReadyModel)
    }
  }, [selectedAsrModelSize, startupCheck])

  useEffect(() => {
    if (!startupCheck?.activeModelDownload.active) {
      return
    }

    const timer = window.setInterval(() => {
      void hydrateStartupCheck()
    }, 1000)

    return () => {
      window.clearInterval(timer)
    }
  }, [hydrateStartupCheck, startupCheck?.activeModelDownload.active])

  function navigateToWorkspace(nextWorkspace: WorkspaceKey) {
    const currentWorkspace = isWorkspaceKey(activeWorkspace) ? activeWorkspace : 'import'

    startTransition(() => {
      if (nextWorkspace === 'settings') {
        if (currentWorkspace !== 'settings') {
          setLastMainWorkspace(currentWorkspace as MainWorkspaceKey)
        }
      } else {
        setLastMainWorkspace(nextWorkspace)
      }

      setActiveWorkspace(nextWorkspace)
      setProcessError(null)
    })
  }

  function handleOutputModeChange(mode: OutputMode) {
    startTransition(() => {
      setFallbackOutputMode(mode)
      setProcessError(null)
      if (config) {
        setConfig(updateOutputMode(config, mode))
      }
    })
  }

  function handleTranscriptionProviderChange(provider: TranscriptionProviderName) {
    startTransition(() => {
      setProcessError(null)
      if (config) {
        setConfig(updateDefaultTranscriptionProvider(config, provider))
      }
    })
  }

  async function handleSaveConfig(nextConfig: AppConfig) {
    const savedConfig = await saveConfig(nextConfig)
    await hydrateConfig()
    await hydrateStartupCheck()

    startTransition(() => {
      setConfig(savedConfig)
      setFallbackOutputMode(savedConfig.outputMode)
      setConfigError(null)
      setProcessError(null)
    })
  }

  async function handleValidateConfig(nextConfig: AppConfig): Promise<string> {
    const result = await validateConfig(nextConfig)
    return result.message
  }

  async function handleValidateSpeechConfig(nextConfig: AppConfig): Promise<string> {
    const result = await validateSpeechConfig(nextConfig)
    return result.message
  }

  async function handleImportResolved(result: ImportResult) {
    const taskRecord = createTaskRecordFromImport(result)
    console.info('[LinguaSub][Import] app:resolved', {
      path: result.currentFile.path,
      route: result.route,
      mediaType: result.currentFile.mediaType,
    })

    startTransition(() => {
      setImportResult(result)
      setProjectState(result.projectState)
      setAgentState(createEmptyAgentSessionState())
      setCurrentTask(taskRecord)
      setImportError(null)
      setProcessError(null)
      setTranscriptionRun(null)
      setTranslationRun(null)
      setExportResult(null)
      setVideoBurnExportResult(null)
      setExportFileName('')
      setSavedSegmentsSnapshot(cloneSegments(result.projectState.segments))
      setLastSavedAt(null)
      setLastMainWorkspace('translation')
      setActiveWorkspace('translation')
    })

    await persistTaskRecord(taskRecord)
  }

  function handleImportFailed(message: string) {
    if (message) {
      console.error('[LinguaSub][Import] app:failed', { message })
    }

    startTransition(() => {
      setImportError(message)
      setProcessError(null)
      if (message) {
        setImportResult(null)
        setProjectState(createEmptyProjectState())
        setAgentState(createEmptyAgentSessionState())
        setCurrentTask(null)
        setTranscriptionRun(null)
        setTranslationRun(null)
        setExportResult(null)
        setVideoBurnExportResult(null)
        setExportFileName('')
        setSavedSegmentsSnapshot([])
        setLastSavedAt(null)
        setLastMainWorkspace('import')
        setActiveWorkspace('import')
      }
    })
  }

  async function handleStartVideoSubtitle() {
    if (!config) {
      setProcessError('当前识别配置尚未加载完成，请稍后再试。')
      return
    }

    const isChineseSingle =
      videoSubtitleDraft.sourceLanguage === 'zh' &&
      videoSubtitleDraft.outputMode === 'single'
    const isEnglishBilingual =
      videoSubtitleDraft.sourceLanguage === 'en' &&
      videoSubtitleDraft.outputMode === 'bilingual'
    const subtitlePathForRun = isEnglishBilingual ? videoSubtitleDraft.subtitlePath : ''

    if (!isChineseSingle && !isEnglishBilingual) {
      setProcessError('当前只支持 中文 + 单语，或 英语 + 双语。')
      return
    }

    if (subtitlePathForRun.trim() && !subtitlePathForRun.trim().toLowerCase().endsWith('.srt')) {
      setProcessError('当前导入字幕分支只支持英文 SRT。请填写 .srt 路径，或清空该输入框继续走英语双语链路。')
      return
    }

    const usingLocalProvider = isLocalSpeechProvider(config.defaultTranscriptionProvider)
    const speechReady =
      hasUsableSpeechConfig(config) &&
      (usingLocalProvider ? startupCheck?.readyForLocalTranscription ?? false : true)

    if (usingLocalProvider && !(startupCheck?.readyForMediaWorkflow ?? false)) {
      setProcessError('当前媒体工作流未就绪，请先确认 FFmpeg 和识别环境可用。')
      return
    }

    if (!speechReady) {
      setProcessError('当前识别配置不可用，请先到设置页补全识别 provider 所需参数。')
      return
    }

    const translationConsistencyIssue =
      isEnglishBilingual ? getTranslationConfigConsistencyIssue(config) : null
    if (translationConsistencyIssue) {
      setProcessError(translationConsistencyIssue)
      return
    }

    if (isEnglishBilingual && !hasUsableTranslationConfig(config)) {
      setProcessError(buildTranslationConfigUserHint(config))
      return
    }

    setIsWorking(true)
    setProcessError(null)

    try {
      const response = await runVideoSubtitle({
        videoPath: videoSubtitleDraft.videoPath,
        subtitlePath: subtitlePathForRun,
        sourceLanguage: videoSubtitleDraft.sourceLanguage,
        outputMode: videoSubtitleDraft.outputMode,
        config,
      })
      const nextImportResult = buildVideoSubtitleImportResult(
        response,
        response.pipeline === 'alignAndTranslate' ? subtitlePathForRun.trim() : null,
      )

      startTransition(() => {
        setImportResult(nextImportResult)
        setImportError(null)
        setAgentState(createEmptyAgentSessionState())
        setProjectState({
          currentFile: { ...response.currentFile },
          segments: cloneSegments(response.segments),
          status: 'done',
          error: null,
        })
        setCurrentTask(null)
        setTranscriptionRun(response.diagnostics.transcription)
        setTranslationRun(
          response.diagnostics.translation
            ? {
                provider: response.diagnostics.translation.provider,
                model: response.diagnostics.translation.model,
                baseUrl: response.diagnostics.translation.baseUrl,
              }
            : null,
        )
        setExportResult(null)
        setVideoBurnExportResult(null)
        setExportFileName('')
        setFallbackOutputMode(response.outputMode)
        setConfig((current) => (current ? updateOutputMode(current, response.outputMode) : current))
        setSavedSegmentsSnapshot(cloneSegments(response.segments))
        setLastSavedAt(formatSaveTime(new Date()))
        setLastMainWorkspace('preview')
        setActiveWorkspace('preview')
      })
    } catch (error) {
      const message =
        error instanceof Error ? error.message : '视频字幕生成失败，请稍后重试。'
      startTransition(() => {
        setProcessError(message)
      })
    } finally {
      setIsWorking(false)
    }
  }

  async function handleStartTranslation(options?: StartTranslationOptions) {
    const activeImportResult = options?.importResultOverride ?? importResult
    const activeProjectState = options?.projectStateOverride ?? projectState
    let activeTask = options?.taskOverride ?? currentTaskRef.current
    let effectiveConfig: AppConfig | null = config

    if (!activeImportResult) {
      setProcessError(m.app.errors.importBeforeTranslation)
      return
    }

    if (!config) {
      setProcessError(m.app.errors.translationConfigMissing)
      return
    }

    if (!hasUsableTranslationConfig(config)) {
      setProcessError(buildTranslationConfigUserHint(config))
      return
    }

    const translationConsistencyIssue = getTranslationConfigConsistencyIssue(config)
    if (translationConsistencyIssue) {
      setProcessError(translationConsistencyIssue)
      return
    }

    if (
      activeImportResult.route === 'recognition' &&
      isCloudSpeechProvider(config.defaultTranscriptionProvider) &&
      !hasUsableSpeechConfig(config)
    ) {
      setProcessError(
        buildSpeechConfigUserHint(
          config as AppConfig,
          (config as AppConfig).defaultTranscriptionProvider,
          selectedAsrModelSize,
        ),
      )
      return
    }

    if (!activeTask) {
      activeTask = await persistTaskRecord(createTaskRecordFromImport(activeImportResult))
    }

    setIsWorking(true)
    setProcessError(null)

    try {
      const persistedConfig = await updateConfig({
        defaultProvider: config.defaultProvider,
        defaultTranscriptionProvider: config.defaultTranscriptionProvider,
        speechProvider: config.defaultTranscriptionProvider,
        apiKey: config.apiKey,
        baseUrl: config.baseUrl,
        model: config.model,
        speechApiKey: config.speechApiKey,
        speechBaseUrl: config.speechBaseUrl,
        speechModel: config.speechModel,
        baiduAppId: config.baiduAppId,
        baiduApiKey: config.baiduApiKey,
        baiduDevPid: config.baiduDevPid,
        baiduCuid: config.baiduCuid,
        tencentAppId: config.tencentAppId,
        tencentSecretId: config.tencentSecretId,
        tencentSecretKey: config.tencentSecretKey,
        tencentEngineModelType: config.tencentEngineModelType,
        outputMode: config.outputMode,
      })
      effectiveConfig = persistedConfig

      startTransition(() => {
        setConfig(persistedConfig)
        setFallbackOutputMode(persistedConfig.outputMode)
        setExportResult(null)
        setVideoBurnExportResult(null)
        setProjectState((current) => ({
          ...current,
          status:
            activeImportResult.route === 'recognition' && current.segments.length === 0
              ? 'transcribing'
              : 'translating',
          error: null,
        }))
      })

      if (activeTask) {
        activeTask = await patchCurrentTask(
          {
            status:
              activeImportResult.route === 'recognition' &&
              activeProjectState.segments.length === 0
                ? 'transcribing'
                : 'translating',
            errorMessage: null,
            translationProvider: persistedConfig.defaultProvider,
            translationModel: persistedConfig.model,
            transcriptionProvider:
              activeImportResult.route === 'recognition'
                ? persistedConfig.defaultTranscriptionProvider
                : activeTask.transcriptionProvider,
            transcriptionModelSize:
              isLocalSpeechProvider(persistedConfig.defaultTranscriptionProvider)
                ? selectedAsrModelSize
                : null,
            transcriptionQualityPreset:
              isLocalSpeechProvider(persistedConfig.defaultTranscriptionProvider)
                ? selectedAsrQualityPreset
                : null,
            outputMode: persistedConfig.outputMode,
          },
          [
            buildTaskLogEntry(
              'info',
              '任务开始处理。',
              `来源文件：${activeImportResult.currentFile.path}`,
            ),
            buildTaskLogEntry(
              'info',
              '已锁定本次识别配置。',
              buildSpeechConfigLogDetails(
                persistedConfig,
                persistedConfig.defaultTranscriptionProvider,
                selectedAsrModelSize,
                selectedAsrQualityPreset,
              ),
            ),
            buildTaskLogEntry(
              'info',
              '已锁定本次翻译配置。',
              buildTranslationConfigLogDetails(persistedConfig),
            ),
            activeImportResult.route === 'recognition'
              ? buildTaskLogEntry(
                  'info',
                  activeImportResult.currentFile.mediaType === 'video'
                    ? '正在读取视频并准备音轨。'
                    : '正在读取音频文件。',
                  `识别方式：${
                    isCloudSpeechProvider(persistedConfig.defaultTranscriptionProvider)
                      ? '云端识别'
                      : '本地识别'
                  }`,
                )
              : buildTaskLogEntry(
                  'info',
                  '正在解析字幕文件。',
                  `字幕文件：${activeImportResult.currentFile.path}`,
                ),
          ],
          activeTask,
        )
      }

      const preparedResult = await prepareSegmentsForTranslation(
        activeImportResult,
        activeProjectState.segments,
        setProjectState,
        m,
        persistedConfig,
        persistedConfig.defaultTranscriptionProvider,
        selectedAsrModelSize,
        selectedAsrLanguage,
        selectedAsrQualityPreset,
      )

      startTransition(() => {
        setProjectState((current) => ({
          ...current,
          segments: preparedResult.segments,
          status: 'translating',
          error: null,
        }))
        if (activeProjectState.segments.length === 0) {
          setAgentState(createEmptyAgentSessionState())
        }
        setTranscriptionRun((current) => preparedResult.transcriptionRun ?? current)
      })

      if (activeTask) {
        const preparedProjectState = {
          currentFile: activeImportResult.currentFile,
          segments: cloneSegments(preparedResult.segments),
          status: 'translating' as const,
          error: null,
        }
        activeTask = await patchCurrentTask(
          {
            status: 'translating',
            errorMessage: null,
            subtitleSummary: buildSubtitleSummary(preparedResult.segments),
            importSnapshot: cloneImportResult(activeImportResult),
            projectSnapshot: preparedProjectState,
          },
              activeImportResult.route === 'recognition'
            ? [
                buildTaskLogEntry(
                  'info',
                  '识别服务调用完成。',
                  `识别服务商：${
                    preparedResult.transcriptionRun?.provider ?? persistedConfig.defaultTranscriptionProvider
                  }\n识别模型：${preparedResult.transcriptionRun?.model ?? 'unknown'}\n识别服务地址：${
                    preparedResult.transcriptionRun?.providerBaseUrl ?? '本地离线模式'
                  }\n检测语言：${preparedResult.transcriptionRun?.detectedLanguage ?? 'auto'}`,
                ),
                buildTaskLogEntry(
                  'info',
                  '已完成文本清洗和断句整理。',
                  `原始片段：${preparedResult.transcriptionRun?.rawSegmentCount ?? preparedResult.segments.length}\n最终片段：${preparedResult.transcriptionRun?.finalSegmentCount ?? preparedResult.segments.length}`,
                ),
              ]
            : [
                buildTaskLogEntry(
                  'info',
                  '字幕文件解析完成。',
                  `已载入 ${preparedResult.segments.length} 条字幕片段。`,
                ),
              ],
          activeTask,
        )
      }

      if (activeTask) {
        activeTask = await patchCurrentTask(
          {
            status: 'translating',
          },
          [
            buildTaskLogEntry(
              'info',
              '正在调用翻译服务。',
              buildTranslationConfigLogDetails(persistedConfig),
            ),
          ],
          activeTask,
        )
      }

      const translationResult = await requestTranslation(
        preparedResult.segments,
        persistedConfig,
      )

      startTransition(() => {
        setProjectState((current) => ({
          ...current,
          segments: translationResult.segments,
          status: 'done',
          error: null,
        }))
        setTranslationRun({
          provider: translationResult.provider,
          model: translationResult.model,
          baseUrl: translationResult.baseUrl,
        })
        setSavedSegmentsSnapshot(cloneSegments(translationResult.segments))
        setLastSavedAt(formatSaveTime(new Date()))
        setActiveWorkspace('preview')
      })

      if (activeTask) {
        await patchCurrentTask(
          {
            status: 'done',
            errorMessage: null,
            subtitleSummary: buildSubtitleSummary(translationResult.segments),
            projectSnapshot: {
              currentFile: activeImportResult.currentFile,
              segments: cloneSegments(translationResult.segments),
              status: 'done',
              error: null,
            },
            translationProvider: translationResult.provider,
            translationModel: translationResult.model,
          },
          [
            buildTaskLogEntry(
              'info',
              '翻译完成，结果已进入预览页。',
              `翻译服务商：${translationResult.provider}\n翻译模型：${translationResult.model}\n翻译服务地址：${translationResult.baseUrl}\n译文片段：${
                buildSubtitleSummary(translationResult.segments).translatedCount
              }/${translationResult.segments.length}`,
            ),
          ],
          activeTask,
        )
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : m.app.errors.translationFlowFailed
      startTransition(() => {
        setProcessError(message)
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })

      if (activeTask) {
        await patchCurrentTask(
          {
            status: 'error',
            errorMessage: message,
            projectSnapshot: {
              currentFile: activeImportResult.currentFile,
              segments: cloneSegments(activeProjectState.segments),
              status: 'error',
              error: message,
            },
          },
          [
            buildTaskLogEntry(
              'error',
              '处理失败。你可以检查日志后重试，或先回到设置页确认识别和翻译配置。',
              [
                effectiveConfig
                  ? buildSpeechConfigLogDetails(
                      effectiveConfig,
                      effectiveConfig.defaultTranscriptionProvider,
                      selectedAsrModelSize,
                      selectedAsrQualityPreset,
                    )
                  : '识别配置：未读取到当前配置',
                effectiveConfig
                  ? buildTranslationConfigLogDetails(effectiveConfig)
                  : '翻译配置：未读取到当前配置',
                `错误详情：${message}`,
              ].join('\n\n'),
            ),
          ],
          activeTask,
        )
      }
    } finally {
      setIsWorking(false)
    }
  }

  async function handleRetranslateSegment(segment: SubtitleSegment) {
    const activeConfig = config ?? createDefaultAppConfig()

    if (!hasUsableTranslationConfig(activeConfig)) {
      throw new Error(buildTranslationConfigUserHint(activeConfig))
    }

    const translationConsistencyIssue = getTranslationConfigConsistencyIssue(activeConfig)
    if (translationConsistencyIssue) {
      throw new Error(translationConsistencyIssue)
    }

    const translationResult = await requestTranslation([segment], activeConfig)
    const updatedSegment = translationResult.segments[0]
    if (!updatedSegment) {
      throw new Error(m.app.errors.missingUpdatedSegment)
    }

    startTransition(() => {
      setProjectState((current) => ({
        ...current,
        segments: current.segments.map((item) =>
          item.id === updatedSegment.id ? updatedSegment : item,
        ),
        error: null,
      }))
      setTranslationRun({
        provider: translationResult.provider,
        model: translationResult.model,
        baseUrl: translationResult.baseUrl,
      })
    })

    await patchCurrentTask(
      {
        translationProvider: translationResult.provider,
        translationModel: translationResult.model,
        subtitleSummary: buildSubtitleSummary(
          projectState.segments.map((item) => (item.id === updatedSegment.id ? updatedSegment : item)),
        ),
      },
      [
        buildTaskLogEntry(
          'info',
          '已重新翻译一条字幕。',
          `字幕 ID：${updatedSegment.id}\n翻译服务商：${translationResult.provider}\n翻译模型：${translationResult.model}\n翻译服务地址：${translationResult.baseUrl}`,
        ),
      ],
    )
  }

  function handleUpdateSegment(
    segmentId: string,
    patch: Pick<SubtitleSegment, 'sourceText' | 'translatedText'>,
  ) {
    startTransition(() => {
      setProjectState((current) => ({
        ...current,
        segments: current.segments.map((segment) =>
          segment.id === segmentId ? { ...segment, ...patch } : segment,
        ),
      }))
    })
  }

  function handleSaveSegments() {
    startTransition(() => {
      setSavedSegmentsSnapshot(cloneSegments(projectState.segments))
      setLastSavedAt(formatSaveTime(new Date()))
    })

    void patchCurrentTask(
      {
        status: 'editing',
        subtitleSummary: buildSubtitleSummary(projectState.segments),
        projectSnapshot: {
          currentFile: projectState.currentFile,
          segments: cloneSegments(projectState.segments),
          status: 'done',
          error: null,
        },
      },
      [
        buildTaskLogEntry(
          'info',
          '已保存当前字幕修改。',
          `保存时间：${new Date().toLocaleString()}`,
        ),
      ],
    )
  }

  function handleSubtitleQualityAgentResultChange(
    result: SubtitleQualityResult,
    segmentSignature: string,
    segmentCount: number,
  ) {
    startTransition(() => {
      setAgentState((current) => ({
        ...current,
        subtitleQuality: {
          result,
          segmentSignature,
          generatedAt: new Date().toISOString(),
          segmentCount,
        },
      }))
    })
  }

  function handleContentSummaryAgentResultChange(
    result: ContentSummaryResult,
    segmentSignature: string,
    segmentCount: number,
  ) {
    startTransition(() => {
      setAgentState((current) => ({
        ...current,
        contentSummary: {
          result,
          segmentSignature,
          generatedAt: new Date().toISOString(),
          segmentCount,
        },
      }))
    })
  }

  function handleSaveCommandAgentResult(item: CommandAgentSessionItem) {
    startTransition(() => {
      setCommandAgentState((current) => ({
        items: [
          item,
          ...current.items.filter((historyItem) => historyItem.id !== item.id),
        ].slice(0, 10),
        activeItemId: item.id,
      }))
    })
  }

  function handleSelectCommandAgentResult(id: string) {
    startTransition(() => {
      setCommandAgentState((current) => {
        if (!current.items.some((item) => item.id === id)) {
          return current
        }

        return {
          ...current,
          activeItemId: id,
        }
      })
    })
  }

  const selectedOutputMode = config?.outputMode ?? fallbackOutputMode
  const currentSegmentSignature = useMemo(
    () => buildAgentSegmentSignature(projectState.segments),
    [projectState.segments],
  )
  const isSubtitleQualityAgentStale =
    agentState.subtitleQuality !== null &&
    agentState.subtitleQuality.segmentSignature !== currentSegmentSignature
  const isContentSummaryAgentStale =
    agentState.contentSummary !== null &&
    agentState.contentSummary.segmentSignature !== currentSegmentSignature
  const currentLanguageLabel = language === 'zh' ? m.common.language.zh : m.common.language.en

  async function handleStartSpeechModelDownload(request: SpeechModelDownloadRequest) {
    setIsModelDownloadStarting(true)

    try {
      await startSpeechModelDownload(request)
      await hydrateStartupCheck()
      startTransition(() => {
        setStartupCheckError(null)
      })
    } catch (error) {
      const message =
        error instanceof Error ? error.message : m.app.errors.startupCheckFailed
      startTransition(() => {
        setStartupCheckError(message)
      })
      throw error instanceof Error ? error : new Error(message)
    } finally {
      setIsModelDownloadStarting(false)
    }
  }

  async function handleStartUninstall() {
    setIsUninstalling(true)
    setUninstallError(null)
    setProcessError(null)

    try {
      await startUninstall()
    } catch (error) {
      const message = error instanceof Error ? error.message : m.app.errors.uninstallStartFailed
      startTransition(() => {
        setUninstallError(message)
      })
      setIsUninstalling(false)
    }
  }

  async function handleExportContentSummaryWord() {
    const storedContentSummary = agentState.contentSummary

    if (!storedContentSummary) {
      const message = m.app.errors.noContentSummaryToExport
      setProcessError(message)
      return
    }

    if (isContentSummaryAgentStale) {
      const message = m.app.errors.staleContentSummaryToExport
      setProcessError(message)
      return
    }

    setIsWorking(true)
    setProcessError(null)

    if (!currentTaskRef.current && importResult) {
      await persistTaskRecord({
        ...createTaskRecordFromImport(importResult),
        projectSnapshot: cloneProjectState(projectState),
        subtitleSummary: buildSubtitleSummary(projectState.segments),
        status: 'editing',
      })
    }

    startTransition(() => {
      setProjectState((current) => ({
        ...current,
        status: 'exporting',
        error: null,
      }))
    })

    try {
      await patchCurrentTask(
        {
          status: 'exporting',
          errorMessage: null,
          outputFormats: Array.from(
            new Set([
              ...(currentTaskRef.current?.outputFormats ?? []),
              'content_summary_word',
            ]),
          ),
        },
        [
          buildTaskLogEntry(
            'info',
            '正在导出内容总结 Word。',
            `文件名：${safeTrim(exportFileName) || '自动命名'}`,
          ),
        ],
      )

      const result = await exportContentSummaryWord({
        summary: storedContentSummary.result,
        sourceFilePath:
          importResult?.currentFile.path ?? projectState.currentFile?.path ?? null,
        fileName: safeTrim(exportFileName) || null,
      })

      startTransition(() => {
        setExportResult(result)
        setProjectState((current) => ({
          ...current,
          status: 'done',
          error: null,
        }))
      })

      await patchCurrentTask(
        {
          status: 'done',
          errorMessage: null,
          exportPaths: Array.from(
            new Set([result.path, ...(currentTaskRef.current?.exportPaths ?? [])]),
          ),
          outputFormats: Array.from(
            new Set([
              ...(currentTaskRef.current?.outputFormats ?? []),
              'content_summary_word',
            ]),
          ),
          projectSnapshot: {
            currentFile: projectState.currentFile,
            segments: cloneSegments(projectState.segments),
            status: 'done',
            error: null,
          },
        },
        [
          buildTaskLogEntry(
            'info',
            result.conflictResolved
              ? '内容总结 Word 导出完成。检测到同名文件后，已自动追加序号保存。'
              : '内容总结 Word 导出完成。',
            `保存路径：${result.path}${
              result.sanitizedFileName ? '\n文件名中的非法字符已自动清洗。' : ''
            }`,
          ),
        ],
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : m.app.errors.exportFailed
      startTransition(() => {
        setProcessError(message)
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })

      await patchCurrentTask(
        {
          status: 'error',
          errorMessage: message,
        },
        [
          buildTaskLogEntry(
            'error',
            '内容总结 Word 导出失败，可能是目标目录无写入权限，或文件正在被其他程序占用。',
            message,
          ),
        ],
      )
    } finally {
      setIsWorking(false)
    }
  }

  async function handleExport(formatOverride?: ExportFormat) {
    const requestedExportFormat = formatOverride ?? selectedExportFormat

    if (requestedExportFormat === 'content_summary_word') {
      await handleExportContentSummaryWord()
      return
    }

    if (projectState.segments.length === 0) {
      const message = m.app.errors.noSubtitleSegmentsToExport
      setProcessError(message)
      startTransition(() => {
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })
      return
    }

    if (
      requestedExportFormat === 'recognition_text' &&
      !projectState.segments.some((segment) => safeTrim(segment.sourceText))
    ) {
      const message = m.app.errors.noRecognitionTextToExport
      setProcessError(message)
      startTransition(() => {
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })
      return
    }

    setIsWorking(true)
    setProcessError(null)

    if (!currentTaskRef.current && importResult) {
      await persistTaskRecord({
        ...createTaskRecordFromImport(importResult),
        projectSnapshot: cloneProjectState(projectState),
        subtitleSummary: buildSubtitleSummary(projectState.segments),
        status: 'editing',
      })
    }

    startTransition(() => {
      setProjectState((current) => ({
        ...current,
        status: 'exporting',
        error: null,
      }))
    })

    try {
      const exportSegments = projectState.segments
      logExportDebugSummary(
        exportSegments,
        requestedExportFormat,
        selectedOutputMode,
      )

      await patchCurrentTask(
        {
          status: 'exporting',
          errorMessage: null,
          outputMode: selectedOutputMode,
          outputFormats: Array.from(
            new Set([
              ...(currentTaskRef.current?.outputFormats ?? []),
              getTaskOutputFormat(
                requestedExportFormat,
                selectedOutputMode,
                selectedWordExportMode,
              ),
            ]),
          ),
        },
        [
          buildTaskLogEntry(
            'info',
            '正在导出文件。',
            `格式：${requestedExportFormat}\n文件名：${
              safeTrim(exportFileName) || '自动命名'
            }`,
          ),
        ],
      )

      const result = await exportSubtitles({
        segments: exportSegments,
        format: requestedExportFormat,
        bilingual: selectedOutputMode === 'bilingual',
        wordMode: selectedWordExportMode,
        sourceFilePath: importResult?.currentFile.path ?? null,
        fileName: safeTrim(exportFileName) || null,
      })

      startTransition(() => {
        setExportResult(result)
        setSavedSegmentsSnapshot(cloneSegments(projectState.segments))
        setLastSavedAt(formatSaveTime(new Date()))
        setProjectState((current) => ({
          ...current,
          status: 'done',
          error: null,
        }))
      })

      await patchCurrentTask(
        {
          status: 'done',
          errorMessage: null,
          exportPaths: Array.from(
            new Set([result.path, ...(currentTaskRef.current?.exportPaths ?? [])]),
          ),
          outputMode: selectedOutputMode,
          projectSnapshot: {
            currentFile: projectState.currentFile,
            segments: cloneSegments(projectState.segments),
            status: 'done',
            error: null,
          },
        },
        [
          buildTaskLogEntry(
            'info',
            result.conflictResolved
              ? '导出完成。检测到同名文件后，已自动追加序号保存。'
              : '导出完成。',
            `保存路径：${result.path}${
              result.sanitizedFileName ? '\n文件名中的非法字符已自动清洗。' : ''
            }`,
          ),
        ],
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : m.app.errors.exportFailed
      startTransition(() => {
        setProcessError(message)
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })

      await patchCurrentTask(
        {
          status: 'error',
          errorMessage: message,
        },
        [
          buildTaskLogEntry(
            'error',
            '导出失败，可能是目标目录无写入权限，或文件正在被其他程序占用。',
            message,
          ),
        ],
      )
    } finally {
      setIsWorking(false)
    }
  }

  async function handleBurnSubtitleVideoExport() {
    if (projectState.segments.length === 0) {
      const message = m.app.errors.noSubtitleSegmentsToExport
      setProcessError(message)
      startTransition(() => {
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })
      return
    }

    const videoPath = getCurrentVideoPath(importResult, projectState)
    if (!videoPath) {
      const message = '当前项目没有原视频路径，无法导出带字幕视频。请从“视频字幕”入口生成字幕后再试。'
      setProcessError(message)
      startTransition(() => {
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })
      return
    }

    let outputPath: string | null = null
    try {
      outputPath = await pickVideoSavePath({
        defaultFileName: buildDefaultBurnedVideoFileName(videoPath),
        defaultPath: buildDefaultBurnedVideoOutputPath(videoPath),
      })
    } catch (error) {
      const message =
        error instanceof Error ? error.message : '无法打开视频另存为窗口，请稍后重试。'
      setProcessError(message)
      return
    }

    if (!outputPath) {
      return
    }

    setIsWorking(true)
    setIsVideoBurnExporting(true)
    setProcessError(null)
    setVideoBurnExportResult(null)

    startTransition(() => {
      setProjectState((current) => ({
        ...current,
        status: 'exporting',
        error: null,
      }))
    })

    try {
      const result = await exportBurnedSubtitleVideo({
        videoPath,
        outputPath,
        segments: projectState.segments,
        mode: videoBurnMode,
      })

      startTransition(() => {
        setVideoBurnExportResult(result)
        setSavedSegmentsSnapshot(cloneSegments(projectState.segments))
        setLastSavedAt(formatSaveTime(new Date()))
        setProjectState((current) => ({
          ...current,
          status: 'done',
          error: null,
        }))
      })

      await patchCurrentTask(
        {
          status: 'done',
          errorMessage: null,
          exportPaths: Array.from(
            new Set([result.outputPath, ...(currentTaskRef.current?.exportPaths ?? [])]),
          ),
          outputMode: selectedOutputMode,
          projectSnapshot: {
            currentFile: projectState.currentFile,
            segments: cloneSegments(projectState.segments),
            status: 'done',
            error: null,
          },
        },
        [
          buildTaskLogEntry(
            'info',
            '带字幕视频导出完成。',
            `保存路径：${result.outputPath}`,
          ),
        ],
      )
    } catch (error) {
      const message =
        error instanceof VideoBurnExportConnectionError
          ? m.app.errors.videoExportConnectionInterrupted
          : error instanceof Error
            ? error.message
            : '导出带字幕视频失败，请稍后重试。'
      startTransition(() => {
        setProcessError(message)
        setProjectState((current) => ({
          ...current,
          status: 'error',
          error: message,
        }))
      })

      await patchCurrentTask(
        {
          status: 'error',
          errorMessage: message,
        },
        [
          buildTaskLogEntry(
            'error',
            '导出带字幕视频失败，可能是 FFmpeg 不可用、源视频路径失效，或目标文件正在被占用。',
            message,
          ),
        ],
      )
    } finally {
      setIsVideoBurnExporting(false)
      setIsWorking(false)
    }
  }

  async function handleOpenHistoryTask(task: TaskHistoryRecord) {
    if (task.status === 'done') {
      restoreTaskState(task, 'preview')
      return
    }

    restoreTaskState(task, 'translation', {
      processErrorOverride: task.errorMessage,
    })
  }

  async function handleRetryHistoryTask(task: TaskHistoryRecord) {
    if (!task.importSnapshot) {
      setHistoryError('该历史任务缺少原始输入信息，请重新导入源文件后再试。')
      return
    }

    const sourceExists = await checkPathExists(task.sourceFilePath)
    if (!sourceExists) {
      setHistoryError(
        '原始文件已不存在或路径失效。请重新导入源文件后再发起重试。',
      )
      return
    }

    const retryProjectState = getInitialProjectStateForRetry(task)
    restoreTaskState(task, 'translation', {
      projectStateOverride: retryProjectState,
      processErrorOverride: null,
    })

    const refreshedTask = await patchCurrentTask(
      {
        status: 'queued',
        errorMessage: null,
        projectSnapshot: cloneProjectState(retryProjectState),
      },
      [
        buildTaskLogEntry(
          'info',
          '已从历史任务重新发起处理。',
          `原始文件：${task.sourceFilePath}`,
        ),
      ],
      task,
    )

    await handleStartTranslation({
      importResultOverride: cloneImportResult(task.importSnapshot),
      projectStateOverride: retryProjectState,
      taskOverride: refreshedTask,
    })
  }

  async function handleExportAgainFromHistory(task: TaskHistoryRecord) {
    if (!task.projectSnapshot || task.projectSnapshot.segments.length === 0) {
      setHistoryError('该历史任务没有可导出的字幕结果，请先重新处理后再导出。')
      return
    }

    restoreTaskState(task, 'export')
  }

  async function handleOpenTaskExportFolder(task: TaskHistoryRecord) {
    const exportPath = task.exportPaths[0]
    if (!exportPath) {
      setHistoryError('该历史任务还没有导出文件，请先重新导出一次。')
      return
    }

    const pathExists = await checkPathExists(exportPath)
    if (!pathExists) {
      setHistoryError(
        '最近一次导出文件可能已经被移动、删除或所在目录失效。请重新导出后再打开文件夹。',
      )
      return
    }

    try {
      await openPathInFileManager(exportPath)
      setHistoryError(null)
    } catch (error) {
      setHistoryError(
        error instanceof Error ? error.message : '无法打开导出目录，请稍后重试。',
      )
    }
  }

  async function handleOpenLatestExportFolder() {
    if (!exportResult) {
      setProcessError('当前还没有导出结果，先完成一次导出后再打开文件夹。')
      return
    }

    try {
      await openPathInFileManager(exportResult.path)
      setProcessError(null)
    } catch (error) {
      setProcessError(
        error instanceof Error ? error.message : '无法打开导出目录，请稍后重试。',
      )
    }
  }

  async function handleOpenLatestVideoBurnExportFolder() {
    if (!videoBurnExportResult) {
      setProcessError('当前还没有带字幕视频导出结果，先完成一次导出后再打开文件夹。')
      return
    }

    try {
      await openPathInFileManager(videoBurnExportResult.outputPath)
      setProcessError(null)
    } catch (error) {
      setProcessError(
        error instanceof Error ? error.message : '无法打开导出目录，请稍后重试。',
      )
    }
  }

  const startupNotice = isBootstrapping
    ? getStartupLoadingNotice(language)
    : resolvedWorkspace !== activeWorkspace
      ? getWorkspaceRecoveryNotice(language)
      : hasStartupRecovery
        ? getStartupRecoveryNotice(language)
        : null

  const workspaceCopy = getWorkspaceCopy(resolvedWorkspace, language, m)
  const headerMetrics = buildHeaderMetrics(
    resolvedWorkspace,
    importResult,
    projectState,
    selectedOutputMode,
    selectedExportFormat,
    selectedWordExportMode,
    config,
    translationRun,
    exportResult,
    language,
    m,
  )
  const sidebarStatus = buildSidebarStatus(
    resolvedWorkspace,
    importResult,
    projectState,
    importError,
    configError,
    processError,
    uninstallError,
    isUninstalling,
    isWorking,
    selectedOutputMode,
    selectedExportFormat,
    selectedWordExportMode,
    exportResult,
    language,
    m,
  )
  const sidebarState = buildSidebarItems(
    resolvedWorkspace,
    importResult,
    projectState,
    isWorking || isUninstalling,
    language,
    m,
  )
  const hasUnsavedChanges = !areSegmentsEqual(projectState.segments, savedSegmentsSnapshot)
  const currentStatusCode =
    resolvedWorkspace === 'settings'
      ? uninstallError || configError
        ? 'error'
        : 'idle'
      : resolvedWorkspace === 'videoSubtitle'
        ? processError || configError
          ? 'error'
          : isWorking
            ? 'transcribing'
            : 'idle'
      : processError || configError
        ? 'error'
        : importResult
          ? projectState.status
          : 'idle'
  const statusLabel = isUninstalling ? m.common.buttons.uninstalling : getStatusLabel(currentStatusCode, m)
  const statusTone =
    uninstallError
      ? 'error'
      : isUninstalling
        ? 'warn'
        : currentStatusCode === 'done'
      ? 'success'
      : currentStatusCode === 'error'
        ? 'error'
        : currentStatusCode === 'transcribing' || currentStatusCode === 'translating' || currentStatusCode === 'exporting'
          ? 'warn'
          : 'idle'
  const statusHint = buildStatusHint(
    resolvedWorkspace,
    importResult,
    projectState,
    importError,
    configError,
    processError,
    uninstallError,
    isUninstalling,
    isWorking,
    selectedOutputMode,
    exportResult,
    language,
    m,
  )
  const actionBarNote = buildActionBarNote(resolvedWorkspace, importResult, m)
  const videoSubtitleProject = isVideoSubtitleImportResult(importResult)

  const secondaryLabel =
    resolvedWorkspace === 'translation'
      ? m.common.buttons.reloadConfig
      : resolvedWorkspace === 'preview'
        ? videoSubtitleProject
          ? language === 'zh'
            ? '返回视频字幕'
            : 'Back to video subtitle'
          : m.common.buttons.translateAgain
        : resolvedWorkspace === 'export'
          ? m.common.buttons.useAutoName
          : resolvedWorkspace === 'settings'
            ? m.common.buttons.reloadConfig
            : m.sidebar.items.settings.label

  const primaryLabel =
    resolvedWorkspace === 'translation'
      ? isWorking
        ? m.common.buttons.working
        : m.common.buttons.startTranslation
      : resolvedWorkspace === 'preview'
        ? m.common.buttons.openExport
      : resolvedWorkspace === 'export'
          ? isWorking
            ? m.common.buttons.exporting
            : getPrimaryExportActionLabel(selectedExportFormat, m)
          : resolvedWorkspace === 'settings'
            ? m.settingsPage.useUninstallPanelAction
          : importResult
            ? m.common.buttons.openTranslationSetup
            : m.common.buttons.importToContinue

  const primaryDisabled =
    resolvedWorkspace === 'translation'
      ? !importResult || !config || isWorking || isConfigLoading
      : resolvedWorkspace === 'preview'
        ? projectState.segments.length === 0
        : resolvedWorkspace === 'export'
          ? projectState.segments.length === 0 || isWorking
          : resolvedWorkspace === 'settings'
            ? true
          : !importResult

  const secondaryDisabled =
    resolvedWorkspace === 'translation'
      ? isWorking || isConfigLoading
      : resolvedWorkspace === 'preview'
        ? false
      : resolvedWorkspace === 'export'
          ? isWorking || safeTrim(exportFileName).length === 0
          : resolvedWorkspace === 'settings'
            ? isConfigLoading || isUninstalling
            : isWorking || isUninstalling

  const previousDisabled =
    resolvedWorkspace === 'import' || isWorking || isUninstalling

  return (
    <div className="app-shell">
      <Sidebar
        items={sidebarState}
        status={sidebarStatus}
        onSelectItem={(key) => {
          navigateToWorkspace(getWorkspaceFromSidebarKey(key))
        }}
      />

      <main className="workspace">
        <StepHeader
          current={workspaceCopy.current}
          total={7}
          title={workspaceCopy.title}
          description={workspaceCopy.description}
          statusLabel={statusLabel}
          statusTone={statusTone}
          statusHint={statusHint}
          metrics={headerMetrics}
          metricsVariant={
            resolvedWorkspace === 'videoSubtitle' ||
            resolvedWorkspace === 'import' ||
            resolvedWorkspace === 'export'
              ? 'chips'
              : 'cards'
          }
        />

        {startupNotice ? (
          <section className="workspace-banner">
            <div
              className={
                startupNotice.tone === 'warn'
                  ? 'warning-banner workspace-banner__surface'
                  : 'info-panel workspace-banner__surface'
              }
            >
              {startupNotice.tone === 'info' ? (
                <span className="startup-spinner" aria-hidden="true" />
              ) : null}
              <div>
                <strong>{startupNotice.title}</strong>
                <p>{startupNotice.description}</p>
              </div>
            </div>
          </section>
        ) : null}

        <section className="workspace-grid">
          {resolvedWorkspace === 'import' ? (
            <ImportWorkspace
              config={config}
              importResult={importResult}
              importError={importError}
              startupCheck={startupCheck}
              startupCheckError={startupCheckError}
              isStartupCheckLoading={isStartupCheckLoading}
              recentTasks={taskHistory}
              isHistoryLoading={isHistoryLoading}
              historyError={historyError}
              selectedTranscriptionProvider={
                config?.defaultTranscriptionProvider ?? 'baidu_realtime'
              }
              selectedAsrModelSize={selectedAsrModelSize}
              selectedAsrLanguage={selectedAsrLanguage}
              selectedAsrQualityPreset={selectedAsrQualityPreset}
              isModelDownloadStarting={isModelDownloadStarting}
              onImportResolved={(result) => {
                return handleImportResolved(result)
              }}
              onImportFailed={handleImportFailed}
              onReloadStartupCheck={() => {
                void hydrateStartupCheck()
              }}
              onOpenSettings={() => {
                navigateToWorkspace('settings')
              }}
              onTranscriptionProviderChange={(provider) => {
                handleTranscriptionProviderChange(provider)
              }}
              onAsrModelSizeChange={(modelSize) => {
                startTransition(() => {
                  setSelectedAsrModelSize(modelSize)
                  setStartupCheckError(null)
                })
              }}
              onAsrLanguageChange={(languageValue) => {
                startTransition(() => {
                  setSelectedAsrLanguage(languageValue)
                  setStartupCheckError(null)
                })
              }}
              onAsrQualityPresetChange={(preset) => {
                startTransition(() => {
                  setSelectedAsrQualityPreset(preset)
                  setStartupCheckError(null)
                })
              }}
              onStartModelDownload={async (request) => {
                await handleStartSpeechModelDownload(request)
              }}
              onOpenRecentTask={(task) => {
                void handleOpenHistoryTask(task)
              }}
              onRetryRecentTask={(task) => {
                void handleRetryHistoryTask(task)
              }}
              onExportRecentTask={(task) => {
                void handleExportAgainFromHistory(task)
              }}
              onOpenTaskExportFolder={(task) => {
                void handleOpenTaskExportFolder(task)
              }}
              onContinue={() => {
                navigateToWorkspace('translation')
              }}
            />
          ) : null}

          {resolvedWorkspace === 'videoSubtitle' ? (
            <VideoSubtitleWorkspace
              draft={videoSubtitleDraft}
              config={config}
              startupCheck={startupCheck}
              isStartupCheckLoading={isStartupCheckLoading}
              isWorking={isWorking}
              processError={processError}
              onDraftChange={(patch) => {
                startTransition(() => {
                  setVideoSubtitleDraft((current) => ({
                    ...current,
                    ...patch,
                  }))
                  setProcessError(null)
                })
              }}
              onOpenSettings={() => {
                navigateToWorkspace('settings')
              }}
              onStart={async () => {
                await handleStartVideoSubtitle()
              }}
            />
          ) : null}

          {resolvedWorkspace === 'translation' ? (
            <TranslationWorkspace
              config={config}
              configError={configError}
              importResult={importResult}
              projectState={projectState}
              transcriptionRun={transcriptionRun}
              isConfigLoading={isConfigLoading}
              isWorking={isWorking}
              processError={processError}
              taskLogs={currentTask?.logs ?? []}
              selectedTranscriptionProvider={
                config?.defaultTranscriptionProvider ?? 'baidu_realtime'
              }
              speechConfigReady={hasUsableSpeechConfig(config)}
              selectedAsrModelSize={selectedAsrModelSize}
              selectedAsrLanguage={selectedAsrLanguage}
              selectedAsrQualityPreset={selectedAsrQualityPreset}
              onProviderChange={(provider) => {
                if (!config) {
                  return
                }

                startTransition(() => {
                  setConfig(selectProvider(config, provider))
                })
              }}
              onModelChange={(model) => {
                if (!config) {
                  return
                }

                startTransition(() => {
                  setConfig(updateActiveProviderModel(config, model))
                })
              }}
              onOutputModeChange={handleOutputModeChange}
              onOpenSettings={() => {
                navigateToWorkspace('settings')
              }}
              onReloadConfig={() => {
                void hydrateConfig()
              }}
            />
          ) : null}

          {resolvedWorkspace === 'preview' ? (
            <SubtitlePreviewWorkspace
              projectState={projectState}
              importResult={importResult}
              config={config}
              translationRun={translationRun}
              taskLogs={currentTask?.logs ?? []}
              hasUnsavedChanges={hasUnsavedChanges}
              lastSavedAt={lastSavedAt}
              currentSegmentSignature={currentSegmentSignature}
              subtitleQualityAgentResult={agentState.subtitleQuality?.result ?? null}
              contentSummaryAgentResult={agentState.contentSummary?.result ?? null}
              isSubtitleQualityAgentStale={isSubtitleQualityAgentStale}
              isContentSummaryAgentStale={isContentSummaryAgentStale}
              onUpdateSegment={handleUpdateSegment}
              onSaveSegments={handleSaveSegments}
              onRetranslateSegment={handleRetranslateSegment}
              onSubtitleQualityAgentResultChange={
                handleSubtitleQualityAgentResultChange
              }
              onContentSummaryAgentResultChange={
                handleContentSummaryAgentResultChange
              }
            />
          ) : null}

          {resolvedWorkspace === 'aiWorkbench' ? (
            <CommandAgentWorkspace
              segments={projectState.segments}
              config={config}
              videoName={getCurrentVideoName(importResult, projectState)}
              videoPath={getCurrentVideoPath(importResult, projectState)}
              sourceLanguage={projectState.segments[0]?.sourceLanguage}
              targetLanguage={projectState.segments[0]?.targetLanguage}
              bilingualMode={selectedOutputMode}
              segmentSignature={currentSegmentSignature}
              commandAgentState={commandAgentState}
              onSaveCommandAgentResult={handleSaveCommandAgentResult}
              onSelectCommandAgentResult={handleSelectCommandAgentResult}
            />
          ) : null}

          {resolvedWorkspace === 'export' ? (
            <ExportWorkspace
              importResult={importResult}
              projectState={projectState}
              exportFormat={selectedExportFormat}
              outputMode={selectedOutputMode}
              wordExportMode={selectedWordExportMode}
              exportFileName={exportFileName}
              exportResult={exportResult}
              videoBurnMode={videoBurnMode}
              videoBurnExportResult={videoBurnExportResult}
              processError={processError}
              isExporting={isWorking && projectState.status === 'exporting'}
              isVideoBurnExporting={isVideoBurnExporting}
              hasUnsavedChanges={hasUnsavedChanges}
              contentSummaryResult={agentState.contentSummary?.result ?? null}
              contentSummaryGeneratedAt={agentState.contentSummary?.generatedAt ?? null}
              isContentSummaryStale={isContentSummaryAgentStale}
              onOpenExportFolder={() => {
                void handleOpenLatestExportFolder()
              }}
              onOpenVideoBurnExportFolder={() => {
                void handleOpenLatestVideoBurnExportFolder()
              }}
              onExportFormatChange={(format) => {
                startTransition(() => {
                  setSelectedExportFormat(format)
                  setExportResult(null)
                  setProcessError(null)
                })
              }}
              onOutputModeChange={handleOutputModeChange}
              onWordExportModeChange={(mode) => {
                startTransition(() => {
                  setSelectedWordExportMode(mode)
                  setExportResult(null)
                  setProcessError(null)
                })
              }}
              onFileNameChange={(value) => {
                startTransition(() => {
                  setExportFileName(value)
                  setProcessError(null)
                })
              }}
              onVideoBurnModeChange={(mode) => {
                startTransition(() => {
                  setVideoBurnMode(mode)
                  setVideoBurnExportResult(null)
                  setProcessError(null)
                })
              }}
              onExportSubtitles={(format) => {
                void handleExport(format)
              }}
              onExportBurnedVideo={() => {
                void handleBurnSubtitleVideoExport()
              }}
              onExportContentSummaryWord={() => {
                void handleExportContentSummaryWord()
              }}
              onClearExportError={() => {
                startTransition(() => {
                  setProcessError(null)
                })
              }}
            />
          ) : null}

          {resolvedWorkspace === 'settings' ? (
            <SettingsWorkspace
              config={config}
              configError={configError}
              isConfigLoading={isConfigLoading}
              managedModelRoots={config?.managedModelRoots ?? []}
              currentLanguageLabel={currentLanguageLabel}
              isUninstalling={isUninstalling}
              uninstallError={uninstallError}
              onSaveConfig={async (nextConfig) => {
                await handleSaveConfig(nextConfig)
              }}
              onValidateConfig={async (nextConfig) => handleValidateConfig(nextConfig)}
              onValidateSpeechConfig={async (nextConfig) =>
                handleValidateSpeechConfig(nextConfig)
              }
              onOpenImport={() => {
                navigateToWorkspace('import')
              }}
              onReloadConfig={() => {
                void hydrateConfig()
              }}
              onStartUninstall={async () => {
                await handleStartUninstall()
              }}
            />
          ) : null}
        </section>

        {resolvedWorkspace !== 'videoSubtitle' &&
        resolvedWorkspace !== 'import' &&
        resolvedWorkspace !== 'export' &&
        resolvedWorkspace !== 'aiWorkbench' ? (
          <ActionBar
            previousLabel={m.common.buttons.previousStep}
            secondaryLabel={secondaryLabel}
            primaryLabel={primaryLabel}
            note={actionBarNote}
            previousDisabled={previousDisabled}
            secondaryDisabled={secondaryDisabled}
            primaryDisabled={primaryDisabled}
            onPreviousClick={() => {
              if (resolvedWorkspace === 'settings') {
                navigateToWorkspace(lastMainWorkspace)
                return
              }

              if (resolvedWorkspace === 'preview') {
                navigateToWorkspace(videoSubtitleProject ? 'videoSubtitle' : 'translation')
                return
              }

              navigateToWorkspace('import')
            }}
            onSecondaryClick={() => {
              if (resolvedWorkspace === 'translation') {
                void hydrateConfig()
                return
              }

              if (resolvedWorkspace === 'preview') {
                navigateToWorkspace(videoSubtitleProject ? 'videoSubtitle' : 'translation')
                return
              }

              if (resolvedWorkspace === 'settings') {
                void hydrateConfig()
                return
              }

              navigateToWorkspace('settings')
            }}
            onPrimaryClick={() => {
              if (resolvedWorkspace === 'translation') {
                void handleStartTranslation()
                return
              }

              if (resolvedWorkspace === 'preview') {
                navigateToWorkspace('export')
                return
              }

              if (resolvedWorkspace === 'settings') {
                return
              }
            }}
          />
        ) : null}
      </main>
    </div>
  )
}

export default App

