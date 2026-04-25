import {
  useEffect,
  useMemo,
  useState,
  type DragEvent,
  type FormEvent,
} from 'react'

import { useI18n } from '../i18n/useI18n'
import { RecentTasksPanel } from './RecentTasksPanel'
import { pickDirectory } from '../services/folderPickerService'
import { pickMediaOrSubtitleFile } from '../services/filePickerService'
import { importFile } from '../services/importService'
import type { SpeechModelDownloadRequest } from '../services/environmentService'
import type {
  DependencyStatus,
  SpeechModelStatus,
  StartupCheckReport,
} from '../types/environment'
import type { ImportResult } from '../types/import'
import type {
  AppConfig,
  AsrModelSize,
  TranscriptionProviderName,
} from '../types/models'
import type { TaskHistoryRecord } from '../types/tasks'
import type { AsrInputLanguage, AsrQualityPreset } from '../types/transcription'
import {
  hasUsableSpeechConfig,
  hasUsableTranslationConfig,
  isCloudSpeechProvider,
  isLocalSpeechProvider,
  safeTrim,
} from '../utils/config'
import { SectionCard } from './SectionCard'

type ImportWorkspaceProps = {
  config: AppConfig | null
  importResult: ImportResult | null
  importError: string | null
  startupCheck: StartupCheckReport | null
  startupCheckError: string | null
  isStartupCheckLoading: boolean
  recentTasks: TaskHistoryRecord[]
  isHistoryLoading: boolean
  historyError: string | null
  selectedTranscriptionProvider: TranscriptionProviderName
  selectedAsrModelSize: AsrModelSize
  selectedAsrLanguage: AsrInputLanguage
  selectedAsrQualityPreset: AsrQualityPreset
  isModelDownloadStarting: boolean
  onImportResolved: (result: ImportResult) => Promise<void> | void
  onImportFailed: (message: string) => void
  onReloadStartupCheck: () => void
  onOpenSettings: () => void
  onTranscriptionProviderChange: (provider: TranscriptionProviderName) => void
  onAsrModelSizeChange: (modelSize: AsrModelSize) => void
  onAsrLanguageChange: (language: AsrInputLanguage) => void
  onAsrQualityPresetChange: (preset: AsrQualityPreset) => void
  onStartModelDownload: (request: SpeechModelDownloadRequest) => Promise<void>
  onOpenRecentTask: (task: TaskHistoryRecord) => void
  onRetryRecentTask: (task: TaskHistoryRecord) => void
  onExportRecentTask: (task: TaskHistoryRecord) => void
  onOpenTaskExportFolder: (task: TaskHistoryRecord) => void
  onContinue: () => void
}

type StorageMode = 'default' | 'custom'
type StatusTone = 'success' | 'warn' | 'idle' | 'error'
type ImportSource = 'manual' | 'picker' | 'drop'

type DependencyCopy = {
  label: string
  requiredFor: string
  details: string
  hint: string
}

type TranscriptionCopy = {
  title: string
  description: string
  providerLabel: string
  cloudHint: string
  localHint: string
  cloudLanguageHint: string
  cloudReadyTitle: string
  cloudSettingsSummary: (model: string, baseUrl: string) => string
  cloudMissingTitle: string
  cloudMissingDescription: string
  cloudSuccessTitle: string
  cloudSuccessDescription: string
  localOptionalTitle: string
  localOptionalDescription: string
}

const SUPPORTED_IMPORT_EXTENSIONS = new Set([
  '.mp4',
  '.mov',
  '.mkv',
  '.mp3',
  '.wav',
  '.m4a',
  '.srt',
])

function getDependencyCopy(
  dependency: DependencyStatus,
  startupCopy: ReturnType<typeof useI18n>['m']['importPage']['environment'],
): DependencyCopy {
  const keyedDependency =
    startupCopy.dependencies[
      dependency.key as keyof typeof startupCopy.dependencies
    ]

  if (keyedDependency) {
    return keyedDependency
  }

  return {
    label: dependency.label,
    requiredFor: dependency.requiredFor,
    details: dependency.details,
    hint: dependency.installHint,
  }
}

function getToneClass(tone: StatusTone): string {
  return `status-pill status-pill--${tone}`
}

function getDependencyTone(available: boolean): StatusTone {
  return available ? 'success' : 'warn'
}

function getModelTone(status: SpeechModelStatus['status']): StatusTone {
  if (status === 'ready') {
    return 'success'
  }

  if (status === 'downloading') {
    return 'idle'
  }

  if (status === 'error') {
    return 'error'
  }

  return 'warn'
}

function getOwnedModelRootPreview(path: string): string {
  const trimmedPath = safeTrim(path).replace(/[\\/]+$/, '')
  if (!trimmedPath) {
    return ''
  }

  const segments = trimmedPath.split(/[\\/]/)
  const lastSegment = segments.at(-1)?.toLowerCase()
  const previousSegment = segments.at(-2)?.toLowerCase()
  if (lastSegment === 'models' && previousSegment === 'linguasub') {
    return trimmedPath
  }

  return `${trimmedPath}\\LinguaSub\\Models`
}

function normalizeImportCandidatePath(rawPath: string): string {
  let normalizedPath = safeTrim(rawPath)
    .split(/\r?\n/)
    .map((line) => safeTrim(line))
    .find((line) => line && !line.startsWith('#')) ?? ''

  normalizedPath = normalizedPath.replace(/^["']+|["']+$/g, '')

  if (!normalizedPath) {
    return ''
  }

  if (normalizedPath.startsWith('file://')) {
    try {
      const fileUrl = new URL(normalizedPath)
      normalizedPath = decodeURIComponent(fileUrl.pathname)
      if (/^\/[A-Za-z]:/.test(normalizedPath)) {
        normalizedPath = normalizedPath.slice(1)
      }
      normalizedPath = normalizedPath.replace(/\//g, '\\')
    } catch (error) {
      console.warn('[LinguaSub][Import] could not parse file URL.', {
        rawPath,
        error,
      })
    }
  }

  return normalizedPath
}

function validateImportPath(
  rawPath: string,
  copy: ReturnType<typeof useI18n>['m'],
): { ok: true; path: string } | { ok: false; error: string } {
  const normalizedPath = normalizeImportCandidatePath(rawPath)
  console.info('[LinguaSub][Import] validate:path', {
    rawPath,
    normalizedPath,
  })

  if (!normalizedPath) {
    return {
      ok: false,
      error: copy.importPage.errors.emptyPath,
    }
  }

  const extension = normalizedPath.match(/\.[^\\/.:]+$/)?.[0]?.toLowerCase() ?? ''
  if (extension && !SUPPORTED_IMPORT_EXTENSIONS.has(extension)) {
    return {
      ok: false,
      error:
        (copy.importPage.errors as Record<string, string | undefined>).unsupportedPathFormat ??
        `暂不支持该文件格式：${extension}`,
    }
  }

  return {
    ok: true,
    path: normalizedPath,
  }
}

function getModelStatusLabel(
  status: SpeechModelStatus['status'],
  m: ReturnType<typeof useI18n>['m'],
): string {
  switch (status) {
    case 'ready':
      return m.common.availability.ready
    case 'downloading':
      return m.common.availability.downloading
    case 'error':
      return m.common.availability.error
    case 'unavailable':
      return m.common.availability.unavailable
    default:
      return m.common.availability.missing
  }
}

function getTranscriptionProviderLabel(
  provider: TranscriptionProviderName,
  m: ReturnType<typeof useI18n>['m'],
): string {
  const labels = (m.common as { transcriptionProviders?: Record<string, string> })
    .transcriptionProviders
  if (labels?.[provider]) {
    return labels[provider]
  }

  if (provider === 'baidu_realtime') {
    return '百度实时识别（推荐）'
  }
  if (provider === 'tencent_realtime') {
    return '腾讯实时识别（预留）'
  }
  if (provider === 'openaiSpeech') {
    return 'OpenAI 兼容识别'
  }
  if (provider === 'localFasterWhisper') {
    return '本地识别（进阶 / 离线）'
  }

  switch (provider) {
    case 'baidu_realtime':
      return '百度实时识别（推荐）'
    case 'tencent_realtime':
      return '腾讯实时识别（预留）'
    case 'openaiSpeech':
      return 'OpenAI 兼容识别'
    default:
      return '本地识别（进阶 / 离线）'
  }
}

function getCloudProviderSummary(config: AppConfig | null, provider: TranscriptionProviderName): string {
  if (provider === 'baidu_realtime') {
    return `当前识别 provider：百度实时识别 / dev_pid=${safeTrim(config?.baiduDevPid) || '未配置'} / endpoint=wss://vop.baidu.com/realtime_asr`
  }

  if (provider === 'tencent_realtime') {
    return `当前识别 provider：腾讯实时识别 / engine_model_type=${safeTrim(config?.tencentEngineModelType) || '未配置'} / endpoint=${
      safeTrim(config?.tencentAppId)
        ? `wss://asr.cloud.tencent.com/asr/v2/${safeTrim(config?.tencentAppId)}`
        : 'wss://asr.cloud.tencent.com/asr/v2/<appid>'
    }`
  }

  if (provider === 'openaiSpeech') {
    return `当前识别 provider：OpenAI 兼容识别 / model=${safeTrim(config?.speechModel) || '未配置'} / endpoint=${safeTrim(config?.speechBaseUrl) || '未配置'}`
  }

  if (provider === 'localFasterWhisper') {
    return '当前使用本地识别模式。'
  }

  if (!config) {
    return '当前还没有读取到识别配置。'
  }

  switch (provider) {
    case 'baidu_realtime':
      return `当前识别 provider：百度实时识别 / dev_pid=${safeTrim(config.baiduDevPid) || '未配置'} / endpoint=wss://vop.baidu.com/realtime_asr`
    case 'tencent_realtime':
      return `当前识别 provider：腾讯实时识别 / engine_model_type=${safeTrim(config.tencentEngineModelType) || '未配置'} / endpoint=${
        safeTrim(config.tencentAppId)
          ? `wss://asr.cloud.tencent.com/asr/v2/${safeTrim(config.tencentAppId)}`
          : 'wss://asr.cloud.tencent.com/asr/v2/<appid>'
      }`
    case 'openaiSpeech':
      return `当前识别 provider：OpenAI 兼容识别 / model=${safeTrim(config.speechModel) || '未配置'} / endpoint=${safeTrim(config.speechBaseUrl) || '未配置'}`
    default:
      return '当前使用本地识别模式。'
  }
}

function getCloudProviderMissingDescription(provider: TranscriptionProviderName): string {
  if (provider === 'baidu_realtime') {
    return '请先到设置页填写百度 AppID、百度 API Key、百度识别模型 PID 和 CUID。'
  }
  if (provider === 'tencent_realtime') {
    return '请先到设置页填写腾讯 AppID、SecretID、SecretKey 和引擎模型类型。'
  }
  if (provider === 'openaiSpeech') {
    return '请先到设置页填写 OpenAI 兼容识别服务地址、API Key 和模型。'
  }
  if (provider === 'localFasterWhisper') {
    return '请先确认本地运行时和模型已经就绪。'
  }

  switch (provider) {
    case 'baidu_realtime':
      return '请先到设置页填写百度 AppID、百度 API Key、百度识别模型 PID 和 CUID。'
    case 'tencent_realtime':
      return '请先到设置页填写腾讯 AppID、SecretID、SecretKey 和引擎模型类型。'
    case 'openaiSpeech':
      return '请先到设置页填写 OpenAI 兼容识别服务地址、API Key 和模型。'
    default:
      return '请先完成当前识别 provider 的配置。'
  }
}

function buildBackendPayload(importResult: ImportResult | null): string | null {
  if (!importResult) {
    return null
  }

  return JSON.stringify(
    {
      route: importResult.route,
      shouldSkipTranscription: importResult.shouldSkipTranscription,
      currentFile: importResult.currentFile,
      recognitionInput: importResult.recognitionInput,
      subtitleInput: importResult.subtitleInput,
    },
    null,
    2,
  )
}

export function ImportWorkspace({
  config,
  importResult,
  importError,
  startupCheck,
  startupCheckError,
  isStartupCheckLoading,
  recentTasks,
  isHistoryLoading,
  historyError,
  selectedTranscriptionProvider,
  selectedAsrModelSize,
  selectedAsrLanguage,
  selectedAsrQualityPreset,
  isModelDownloadStarting,
  onImportResolved,
  onImportFailed,
  onReloadStartupCheck,
  onOpenSettings,
  onTranscriptionProviderChange,
  onAsrModelSizeChange,
  onAsrLanguageChange,
  onAsrQualityPresetChange,
  onStartModelDownload,
  onOpenRecentTask,
  onRetryRecentTask,
  onExportRecentTask,
  onOpenTaskExportFolder,
  onContinue,
}: ImportWorkspaceProps) {
  const { m, language } = useI18n()
  const rawTranscriptionCopy = (
    m.importPage.environment as { transcription?: Partial<TranscriptionCopy> }
  ).transcription
  const transcriptionCopy: TranscriptionCopy = {
    title: rawTranscriptionCopy?.title ?? 'Cloud / Local transcription',
    description:
      rawTranscriptionCopy?.description ??
      'Use cloud transcription as the recommended route for normal users, or switch to local faster-whisper for advanced offline work.',
    providerLabel: rawTranscriptionCopy?.providerLabel ?? 'Transcription mode',
    cloudHint:
      rawTranscriptionCopy?.cloudHint ??
      'Cloud transcription is recommended. It needs an API key, but does not depend on local model downloads.',
    localHint:
      rawTranscriptionCopy?.localHint ??
      'Local transcription is advanced/offline. It needs FFmpeg, faster-whisper, and a downloaded local model.',
    cloudLanguageHint:
      rawTranscriptionCopy?.cloudLanguageHint ??
      'If you already know the source language, pass it to cloud transcription to reduce wrong-language recognition.',
    cloudReadyTitle:
      rawTranscriptionCopy?.cloudReadyTitle ?? 'Cloud transcription settings',
    cloudSettingsSummary:
      typeof rawTranscriptionCopy?.cloudSettingsSummary === 'function'
        ? rawTranscriptionCopy.cloudSettingsSummary
        : (model: string, baseUrl: string) => `Current cloud model: ${model} / ${baseUrl}`,
    cloudMissingTitle:
      rawTranscriptionCopy?.cloudMissingTitle ?? 'Cloud transcription is not ready yet',
    cloudMissingDescription:
      rawTranscriptionCopy?.cloudMissingDescription ??
      'Open Settings and save the OpenAI Speech-to-Text API key, base URL, and model before using the recommended route.',
    cloudSuccessTitle:
      rawTranscriptionCopy?.cloudSuccessTitle ?? 'Cloud transcription is ready',
    cloudSuccessDescription:
      rawTranscriptionCopy?.cloudSuccessDescription ??
      'You can start media -> cloud transcription -> translation now, without waiting for local model downloads.',
    localOptionalTitle:
      rawTranscriptionCopy?.localOptionalTitle ?? 'Local transcription stays available',
    localOptionalDescription:
      rawTranscriptionCopy?.localOptionalDescription ??
      'Switch back to local faster-whisper any time if you need offline processing or tighter local control.',
  }
  const summaryLabels = (m.common.summary as Record<string, string | undefined>) ?? {}
  const safeRecentTasks = Array.isArray(recentTasks) ? recentTasks : []
  const [pathValue, setPathValue] = useState(importResult?.currentFile.path ?? '')
  const [isInspecting, setIsInspecting] = useState(false)
  const [isDownloadDialogOpen, setIsDownloadDialogOpen] = useState(false)
  const [storageMode, setStorageMode] = useState<StorageMode>('default')
  const [customStoragePath, setCustomStoragePath] = useState('')
  const [rememberStoragePath, setRememberStoragePath] = useState(true)
  const [downloadDialogError, setDownloadDialogError] = useState<string | null>(null)
  const [isPickingDirectory, setIsPickingDirectory] = useState(false)
  const [isPickingFile, setIsPickingFile] = useState(false)
  const [isDragActive, setIsDragActive] = useState(false)
  const [, setDragDepth] = useState(0)

  const backendPayload = useMemo(() => buildBackendPayload(importResult), [importResult])
  const selectedModel =
    startupCheck?.speechModels.find((model) => model.size === selectedAsrModelSize) ?? null
  const cloudTranscriptionReady =
    startupCheck?.readyForCloudTranscription ?? hasUsableSpeechConfig(config)
  const localTranscriptionReady = startupCheck?.readyForLocalTranscription ?? false
  const fasterWhisperRuntimeReady =
    startupCheck?.dependencies.some(
      (dependency) => dependency.key === 'fasterWhisperRuntime' && dependency.available,
    ) ?? false
  const downloadStatus = startupCheck?.activeModelDownload ?? null
  const resolvedModelStoragePath =
    downloadStatus?.targetPath ?? startupCheck?.speechModelStorageDir ?? null
  const usingDefaultStorage =
    downloadStatus?.targetPath != null
      ? downloadStatus.usingDefaultStorage
      : startupCheck
        ? startupCheck.speechModelStorageDir === startupCheck.defaultSpeechModelStorageDir
        : true
  const canStartModelDownload =
    Boolean(startupCheck) &&
    fasterWhisperRuntimeReady &&
    !isModelDownloadStarting &&
    !downloadStatus?.active
  const translationApiReady = hasUsableTranslationConfig(config)
  const onboardingCopy =
    language === 'zh'
      ? {
          heroTitle: '选择一个源文件',
          heroDescription: '拖入文件，或点击按钮从本机选择。',
          dragHint: '支持 MP4、MOV、MKV、MP3、WAV、M4A、SRT',
          pickFile: '选择文件',
          firstUseTitle: '首次使用建议',
          apiMissingTitle: '首次使用前，请先完成 API 配置',
          apiMissingDescription:
            '这样你就可以直接走“导入媒体 -> 云端识别 -> 翻译 -> 预览 -> 导出”的推荐主路径。',
          apiReadyTitle: 'API 已准备好',
          apiReadyDescription:
            '现在可以直接导入媒体或 SRT，验证主流程是否可用。',
          cloudRecommended: '商业 API：更稳定，推荐多数测试用户使用',
          localAdvanced: '本地识别：适合进阶用户，首次使用可能需要下载模型',
        }
      : {
          heroTitle: 'Choose a source file',
          heroDescription: 'Drop a file here, or choose one from this computer.',
          dragHint: 'MP4, MOV, MKV, MP3, WAV, M4A, and SRT are supported.',
          pickFile: 'Choose file',
          firstUseTitle: 'Recommended first-use path',
          apiMissingTitle: 'Finish API setup before your first translation test',
          apiMissingDescription:
            'That lets you verify the recommended media -> cloud transcription -> translation -> preview -> export path without extra local setup.',
          apiReadyTitle: 'API setup looks ready',
          apiReadyDescription:
            'You can now import media or SRT and verify the main workflow directly.',
          cloudRecommended: 'Commercial API: more stable and recommended for most users',
          localAdvanced:
            'Local transcription: better for advanced offline use and may need model downloads',
        }

  useEffect(() => {
    if (importResult?.currentFile.path) {
      setPathValue(importResult.currentFile.path)
    }
  }, [importResult?.currentFile.path])

  async function submitImport(rawPath: string, source: ImportSource) {
    console.info('[LinguaSub][Import] submit:start', {
      source,
      rawPath,
    })

    const validation = validateImportPath(rawPath, m)
    if (!validation.ok) {
      console.warn('[LinguaSub][Import] submit:invalid', {
        source,
        rawPath,
        error: validation.error,
      })
      onImportFailed(validation.error)
      return
    }

    setPathValue(validation.path)
    setIsInspecting(true)
    onImportFailed('')

    try {
      console.info('[LinguaSub][Import] submit:request', {
        source,
        path: validation.path,
      })
      const result = await importFile(validation.path)
      console.info('[LinguaSub][Import] submit:success', {
        source,
        path: validation.path,
        route: result.route,
        mediaType: result.currentFile.mediaType,
      })
      await onImportResolved(result)
    } catch (error) {
      const message =
        error instanceof Error ? error.message : m.app.errors.translationFlowFailed
      console.error('[LinguaSub][Import] submit:failed', {
        source,
        path: validation.path,
        error,
      })
      onImportFailed(message)
    } finally {
      setIsInspecting(false)
    }
  }

  async function handleImportSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await submitImport(pathValue, 'manual')
  }

  async function handlePickFile() {
    setIsPickingFile(true)
    try {
      const pickedPath = await pickMediaOrSubtitleFile()
      console.info('[LinguaSub][Import] picker:result', { pickedPath })
      if (pickedPath) {
        await submitImport(pickedPath, 'picker')
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : m.common.misc.importFailed
      console.error('[LinguaSub][Import] picker:failed', error)
      onImportFailed(message)
    } finally {
      setIsPickingFile(false)
    }
  }

  function resetDragState() {
    setDragDepth(0)
    setIsDragActive(false)
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()

    if (!event.dataTransfer.types.includes('Files')) {
      return
    }

    setDragDepth((current) => current + 1)
    setIsDragActive(true)
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    if (!event.dataTransfer.types.includes('Files')) {
      return
    }

    event.dataTransfer.dropEffect = 'copy'
    setIsDragActive(true)
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()

    setDragDepth((current) => {
      const nextDepth = Math.max(0, current - 1)
      if (nextDepth === 0) {
        setIsDragActive(false)
      }
      return nextDepth
    })
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    resetDragState()

    const fileCount = event.dataTransfer.files?.length ?? 0
    if (fileCount > 1) {
      onImportFailed(
        (m.importPage.errors as Record<string, string | undefined>).multipleFilesNotSupported ??
          '当前一次只支持导入一个文件，请只拖入一个视频、音频或字幕文件。',
      )
      return
    }

    const file = event.dataTransfer.files?.[0] as (File & { path?: string }) | undefined
    const uriPath = event.dataTransfer.getData('text/uri-list')
    const plainPath = event.dataTransfer.getData('text/plain')
    const droppedPath = file?.path || uriPath || plainPath

    console.info('[LinguaSub][Import] drop:result', {
      fileCount,
      droppedPath,
      fileName: file?.name ?? null,
    })

    if (!droppedPath) {
      onImportFailed(
        (m.importPage.errors as Record<string, string | undefined>).dropPathMissing ??
          '没有读取到可导入的本地文件路径，请重试或改用“选择文件”。',
      )
      return
    }

    await submitImport(droppedPath, 'drop')
  }

  function openDownloadDialog() {
    if (!startupCheck) {
      return
    }

    const hasCustomStorage =
      startupCheck.speechModelStorageDir !== startupCheck.defaultSpeechModelStorageDir

    setStorageMode(hasCustomStorage ? 'custom' : 'default')
    setCustomStoragePath(
      hasCustomStorage
        ? startupCheck.speechModelStorageDir
        : startupCheck.defaultSpeechModelStorageDir,
    )
    setRememberStoragePath(true)
    setDownloadDialogError(null)
    setIsDownloadDialogOpen(true)
  }

  async function handlePickDirectory() {
    const fallbackPath =
      (storageMode === 'custom' ? safeTrim(customStoragePath) : '') ||
      startupCheck?.speechModelStorageDir ||
      startupCheck?.defaultSpeechModelStorageDir ||
      null

    setIsPickingDirectory(true)
    setDownloadDialogError(null)

    try {
      const selectedDirectory = await pickDirectory(fallbackPath)
      if (selectedDirectory) {
        setStorageMode('custom')
        setCustomStoragePath(selectedDirectory)
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : m.importPage.environment.models.pickerFailed
      setDownloadDialogError(message)
    } finally {
      setIsPickingDirectory(false)
    }
  }

  async function handleConfirmDownload() {
    const storagePath =
      storageMode === 'custom' ? safeTrim(customStoragePath) : null

    if (storageMode === 'custom' && !storagePath) {
      setDownloadDialogError(m.importPage.environment.models.customPathRequired)
      return
    }

    setDownloadDialogError(null)

    try {
      await onStartModelDownload({
        modelSize: selectedAsrModelSize,
        storagePath,
        rememberStoragePath,
      })
      setIsDownloadDialogOpen(false)
    } catch (error) {
      const message =
        error instanceof Error ? error.message : m.app.errors.startupCheckFailed
      setDownloadDialogError(message)
    }
  }

  return (
    <>
      <SectionCard
        eyebrow={m.importPage.sections.import.eyebrow}
        title={m.importPage.sections.import.title}
        description={m.importPage.sections.import.description}
        className="span-12 import-workspace"
      >
        <form className="import-form import-form--focused" onSubmit={handleImportSubmit}>
          <div className="import-layout">
            <div className="import-layout__primary">
              <div
            className={`import-dropzone${isDragActive ? ' import-dropzone--active' : ''}`}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={(event) => {
              void handleDrop(event)
            }}
          >
            <span className="import-dropzone__eyebrow">{m.importPage.supportedInputLabel}</span>
            <h3>{onboardingCopy.heroTitle}</h3>
            <p>
              {isDragActive
                ? language === 'zh'
                  ? '松开即可直接导入文件'
                  : 'Release to import the file directly'
                : onboardingCopy.heroDescription}
            </p>
            <div className="inline-actions">
              <button
                type="button"
                className="button button--primary"
                onClick={() => {
                  void handlePickFile()
                }}
                disabled={isPickingFile || isInspecting}
              >
                {isPickingFile ? m.common.misc.loading : onboardingCopy.pickFile}
              </button>
            </div>
            <p className="helper-text">
              {isDragActive
                ? language === 'zh'
                  ? '支持单文件拖拽，松开后会立即校验并开始导入'
                  : 'Drop one file to validate it and start importing immediately'
                : onboardingCopy.dragHint}
            </p>
          </div>

          <details className="import-manual-path">
            <summary>
              {language === 'zh' ? '也可以粘贴本地路径' : 'Paste a local path instead'}
            </summary>
            <label className="field-block">
              <span className="field-label">{m.importPage.localPath}</span>
              <div className="input-row">
                <input
                  className="text-input"
                  type="text"
                  value={pathValue}
                  onChange={(event) => setPathValue(event.target.value)}
                  placeholder={m.common.placeholders.importPath}
                  spellCheck={false}
                />
                <button
                  type="submit"
                  className="button button--secondary"
                  disabled={isInspecting}
                >
                  {isInspecting ? m.common.buttons.inspecting : m.common.buttons.importFile}
                </button>
              </div>
              <span className="helper-text">{m.importPage.helperText}</span>
            </label>
          </details>

              {importError ? (
                <div className="error-banner" role="alert">
                  <strong>{m.common.misc.importFailed}</strong>
                  <p>{importError}</p>
                </div>
              ) : null}
            </div>

            <div className="import-layout__aside">
              <div className={`import-file-panel${importResult ? '' : ' import-file-panel--empty'}`}>
            {importResult ? (
              <>
                <div className="import-file-panel__head">
                  <div>
                    <span className="field-label">
                      {language === 'zh' ? '已导入文件' : 'Imported file'}
                    </span>
                    <h3>{importResult.currentFile.name}</h3>
                  </div>
                  <button
                    type="button"
                    className="button button--primary"
                    onClick={onContinue}
                  >
                    {language === 'zh' ? '继续处理' : 'Continue'}
                  </button>
                </div>
                <div className="import-file-grid">
                  <div>
                    <span className="summary-item__label">{m.common.summary.type}</span>
                    <strong>{m.importPage.mediaTypes[importResult.currentFile.mediaType]}</strong>
                  </div>
                  <div>
                    <span className="summary-item__label">{m.common.summary.path}</span>
                    <strong>{importResult.currentFile.path}</strong>
                  </div>
                  <div>
                    <span className="summary-item__label">
                      {language === 'zh' ? '下一步' : 'Next step'}
                    </span>
                    <strong>
                      {importResult.route === 'recognition'
                        ? m.app.routes.recognitionToTranslation
                        : m.app.routes.srtParseToTranslation}
                    </strong>
                  </div>
                </div>
              </>
            ) : (
              <div className="import-empty-state">
                <h3>{m.importPage.emptySummaryTitle}</h3>
                <p>{m.importPage.emptySummaryDescription}</p>
              </div>
            )}
              </div>
            </div>
          </div>

          <details className="import-details">
          <summary>
            {language === 'zh'
              ? '查看支持格式与环境信息'
              : 'View supported formats and environment details'}
          </summary>

          <div className="import-details__body">
            <section className="import-details__section">
              <h3>{language === 'zh' ? '支持格式' : 'Supported formats'}</h3>
              <div className="summary-grid">
                {m.importPage.formatGroups.map((group) => (
                  <div key={group.title} className="summary-item">
                    <span className="summary-item__label">{group.title}</span>
                    <span className="summary-item__value">{group.items.join(' / ')}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="import-details__section">
              <h3>{language === 'zh' ? '导入后的处理路径' : 'Processing route after import'}</h3>
              {importResult ? (
                <div className="info-panel">
                  <strong>{m.common.summary.route}</strong>
                  <p>
                    {importResult.workflow
                      .map(
                        (step) =>
                          m.common.workflowSteps[
                            step as keyof typeof m.common.workflowSteps
                          ] ?? step,
                      )
                      .join(' -> ')}
                  </p>
                </div>
              ) : (
                <p className="helper-text">{m.importPage.workflowWaitingDescription}</p>
              )}
              <div className="quick-actions">
                {m.importPage.workflowExamples.map((example) => (
                  <article key={example.title} className="action-tile">
                    <strong className="action-tile__title">{example.title}</strong>
                    <p>{example.description}</p>
                    <span className="helper-text">{example.steps.join(' -> ')}</span>
                  </article>
                ))}
              </div>
            </section>

            <section className="import-details__section">
              <h3>{language === 'zh' ? '环境与识别设置' : 'Environment and recognition settings'}</h3>
              {isStartupCheckLoading && !startupCheck ? (
                <div className="empty-state">
                  <h3>{m.importPage.noEnvironmentTitle}</h3>
                  <p>{m.importPage.noEnvironmentDescription}</p>
                </div>
              ) : null}

              {startupCheck ? (
                <>
                  <div className="summary-grid">
                    <div className="summary-item">
                      <span className="summary-item__label">{m.common.summary.backend}</span>
                      <span className="summary-item__value">
                        {startupCheck.backendReachable
                          ? m.importPage.environment.backendReachable
                          : m.importPage.environment.backendUnreachable}
                      </span>
                    </div>
                    <div className="summary-item">
                      <span className="summary-item__label">{m.common.summary.mediaWorkflow}</span>
                      <span className="summary-item__value">
                        {startupCheck.readyForMediaWorkflow
                          ? m.importPage.environment.mediaReady
                          : m.importPage.environment.mediaMissing}
                      </span>
                    </div>
                    <div className="summary-item">
                      <span className="summary-item__label">
                        {summaryLabels.cloudTranscription ?? 'Cloud transcription'}
                      </span>
                      <span className="summary-item__value">
                        {cloudTranscriptionReady
                          ? m.common.availability.available
                          : m.common.availability.missing}
                      </span>
                    </div>
                    <div className="summary-item">
                      <span className="summary-item__label">
                        {summaryLabels.localTranscription ?? 'Local transcription'}
                      </span>
                      <span className="summary-item__value">
                        {localTranscriptionReady
                          ? m.common.availability.available
                          : m.common.availability.missing}
                      </span>
                    </div>
                    <div className="summary-item">
                      <span className="summary-item__label">{m.common.summary.srtWorkflow}</span>
                      <span className="summary-item__value">
                        {startupCheck.readyForSrtWorkflow
                          ? m.importPage.environment.srtReady
                          : m.importPage.environment.srtBlocked}
                      </span>
                    </div>
                    <div className="summary-item">
                      <span className="summary-item__label">{m.common.summary.speechModelFolder}</span>
                      <span className="summary-item__value">{startupCheck.speechModelStorageDir}</span>
                    </div>
                  </div>

                  {!translationApiReady ? (
                    <div className="warning-banner" role="alert">
                      <strong>{onboardingCopy.apiMissingTitle}</strong>
                      <p>{onboardingCopy.apiMissingDescription}</p>
                      <div className="inline-actions">
                        <button
                          type="button"
                          className="button button--secondary"
                          onClick={onOpenSettings}
                        >
                          {m.translationPage.openSettingsAction}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="success-banner" role="status">
                      <strong>{onboardingCopy.apiReadyTitle}</strong>
                      <p>{onboardingCopy.apiReadyDescription}</p>
                    </div>
                  )}

                  {startupCheck.warnings.length > 0 ? (
                    <div className="warning-banner" role="alert">
                      <strong>{m.importPage.environment.startupWarnings}</strong>
                      <ul className="notice-list">
                        {startupCheck.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="success-banner" role="status">
                      <strong>{m.importPage.environment.startupSuccessTitle}</strong>
                      <p>{m.importPage.environment.startupSuccessDescription}</p>
                    </div>
                  )}

                  {startupCheck.actions.length > 0 ? (
                    <div className="info-panel">
                      <strong>{m.importPage.environment.nextActions}</strong>
                      <ul className="notice-list">
                        {startupCheck.actions.map((action) => (
                          <li key={action}>{action}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  <div className="dependency-list">
                    {startupCheck.dependencies.map((dependency) => {
                      const copy = getDependencyCopy(dependency, m.importPage.environment)
                      return (
                        <article key={dependency.key} className="dependency-card">
                          <div className="dependency-card__head">
                            <div>
                              <h3>{copy.label}</h3>
                              <p>{copy.requiredFor}</p>
                            </div>
                            <span className={getToneClass(getDependencyTone(dependency.available))}>
                              {dependency.available
                                ? m.common.availability.available
                                : m.common.availability.missing}
                            </span>
                          </div>
                          <p className="dependency-card__details">
                            {dependency.details || copy.details}
                          </p>
                          <p className="dependency-card__details">{copy.hint}</p>
                          <p className="dependency-card__path">
                            {dependency.detectedPath ?? m.common.misc.notRecorded}
                          </p>
                        </article>
                      )
                    })}
                  </div>

                  <div className="model-panel">
                    <div className="model-panel__head">
                      <div>
                        <h3>{transcriptionCopy.title}</h3>
                        <p>{transcriptionCopy.description}</p>
                      </div>
                      <span
                        className={getToneClass(
                          isCloudSpeechProvider(selectedTranscriptionProvider)
                            ? cloudTranscriptionReady
                              ? 'success'
                              : 'warn'
                            : selectedModel
                              ? getModelTone(selectedModel.status)
                              : 'warn',
                        )}
                      >
                        {isCloudSpeechProvider(selectedTranscriptionProvider)
                          ? cloudTranscriptionReady
                            ? m.common.availability.available
                            : m.common.availability.missing
                          : selectedModel
                            ? getModelStatusLabel(selectedModel.status, m)
                            : m.common.availability.missing}
                      </span>
                    </div>

                    <div className="model-panel__controls">
                      <label className="model-panel__field">
                        <span className="field-label">
                          {transcriptionCopy.providerLabel}
                        </span>
                        <select
                          className="select-input"
                          value={selectedTranscriptionProvider}
                          onChange={(event) =>
                            onTranscriptionProviderChange(
                              event.target.value as TranscriptionProviderName,
                            )
                          }
                        >
                          <option value="baidu_realtime">
                            {getTranscriptionProviderLabel('baidu_realtime', m)}
                          </option>
                          <option value="tencent_realtime">
                            {getTranscriptionProviderLabel('tencent_realtime', m)}
                          </option>
                          <option value="openaiSpeech">
                            {getTranscriptionProviderLabel('openaiSpeech', m)}
                          </option>
                          <option value="localFasterWhisper">
                            {getTranscriptionProviderLabel('localFasterWhisper', m)}
                          </option>
                        </select>
                        <span className="helper-text">
                          {isCloudSpeechProvider(selectedTranscriptionProvider)
                            ? transcriptionCopy.cloudHint
                            : transcriptionCopy.localHint}
                        </span>
                      </label>

                      <label className="model-panel__field">
                        <span className="field-label">
                          {m.importPage.environment.models.languageLabel}
                        </span>
                        <select
                          className="select-input"
                          value={selectedAsrLanguage}
                          onChange={(event) =>
                            onAsrLanguageChange(event.target.value as AsrInputLanguage)
                          }
                        >
                          <option value="auto">{m.common.asrLanguages.auto}</option>
                          <option value="zh">{m.common.asrLanguages.zh}</option>
                          <option value="en">{m.common.asrLanguages.en}</option>
                          <option value="ja">{m.common.asrLanguages.ja}</option>
                          <option value="ko">{m.common.asrLanguages.ko}</option>
                        </select>
                        <span className="helper-text">
                          {isCloudSpeechProvider(selectedTranscriptionProvider)
                            ? transcriptionCopy.cloudLanguageHint
                            : m.importPage.environment.models.languageHint}
                        </span>
                      </label>

                      {isLocalSpeechProvider(selectedTranscriptionProvider) ? (
                        <>
                          <label className="model-panel__field">
                            <span className="field-label">
                              {m.importPage.environment.models.selectLabel}
                            </span>
                            <select
                              className="select-input"
                              value={selectedAsrModelSize}
                              onChange={(event) =>
                                onAsrModelSizeChange(event.target.value as AsrModelSize)
                              }
                            >
                              {startupCheck.speechModels.map((model) => (
                                <option key={model.size} value={model.size}>
                                  {m.importPage.environment.models.optionLabel(
                                    model.label,
                                    getModelStatusLabel(model.status, m),
                                  )}
                                </option>
                              ))}
                            </select>
                          </label>

                          <label className="model-panel__field">
                            <span className="field-label">
                              {m.importPage.environment.models.qualityLabel}
                            </span>
                            <select
                              className="select-input"
                              value={selectedAsrQualityPreset}
                              onChange={(event) =>
                                onAsrQualityPresetChange(event.target.value as AsrQualityPreset)
                              }
                            >
                              <option value="speed">{m.common.asrQualityPresets.speed}</option>
                              <option value="balanced">{m.common.asrQualityPresets.balanced}</option>
                              <option value="accuracy">{m.common.asrQualityPresets.accuracy}</option>
                            </select>
                            <span className="helper-text">
                              {
                                m.importPage.environment.models.qualityDescriptions[
                                  selectedAsrQualityPreset
                                ]
                              }
                            </span>
                          </label>

                          <button
                            type="button"
                            className="button button--primary"
                            onClick={openDownloadDialog}
                            disabled={!canStartModelDownload}
                          >
                            {isModelDownloadStarting
                              ? m.common.buttons.downloadingModel
                              : m.common.buttons.downloadModel}
                          </button>
                        </>
                      ) : null}
                    </div>

                    {isCloudSpeechProvider(selectedTranscriptionProvider) ? (
                      <>
                        <div className="info-panel">
                          <strong>{transcriptionCopy.cloudReadyTitle}</strong>
                          <p>{getCloudProviderSummary(config, selectedTranscriptionProvider)}</p>
                        </div>

                        {!cloudTranscriptionReady ? (
                          <div className="warning-banner" role="alert">
                            <strong>
                              {transcriptionCopy.cloudMissingTitle}
                            </strong>
                            <p>{getCloudProviderMissingDescription(selectedTranscriptionProvider)}</p>
                            <div className="inline-actions">
                              <button
                                type="button"
                                className="button button--secondary"
                                onClick={onOpenSettings}
                              >
                                {m.translationPage.openSettingsAction}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="success-banner" role="status">
                            <strong>
                              {transcriptionCopy.cloudSuccessTitle}
                            </strong>
                            <p>
                              {transcriptionCopy.cloudSuccessDescription}
                            </p>
                          </div>
                        )}

                        <div className="info-panel">
                          <strong>
                            {transcriptionCopy.localOptionalTitle}
                          </strong>
                          <p>
                            {transcriptionCopy.localOptionalDescription}
                          </p>
                        </div>
                      </>
                    ) : null}

                    {isLocalSpeechProvider(selectedTranscriptionProvider) ? (
                      <>
                        <div className="model-grid">
                          {startupCheck.speechModels.map((model) => (
                            <article key={model.size} className="dependency-card">
                              <div className="dependency-card__head">
                                <div>
                                  <h3>{m.importPage.environment.models.modelLabel(model.label)}</h3>
                                  <p>{model.statusText}</p>
                                </div>
                                <span className={getToneClass(getModelTone(model.status))}>
                                  {getModelStatusLabel(model.status, m)}
                                </span>
                              </div>
                              <p className="dependency-card__details">{model.details}</p>
                              <p className="dependency-card__details">{model.actionHint}</p>
                              <p className="dependency-card__path">
                                {model.detectedPath ?? m.common.misc.notRecorded}
                              </p>
                            </article>
                          ))}
                        </div>

                        <p className="helper-text">
                          {usingDefaultStorage
                            ? m.importPage.environment.models.storageHint(
                                startupCheck.defaultSpeechModelStorageDir,
                              )
                            : m.importPage.environment.models.selectedStorageHint(
                                startupCheck.speechModelStorageDir,
                              )}
                        </p>

                        {downloadStatus?.active ? (
                          <div className="download-progress" role="status">
                            <div className="download-progress__head">
                              <strong>
                                {m.importPage.environment.models.downloadStatusTitle}
                              </strong>
                              <span>
                                {Math.min(100, Math.max(0, downloadStatus.progress))}%
                              </span>
                            </div>
                            <p>
                              {m.importPage.environment.models.downloadModelName(
                                downloadStatus.modelSize ?? selectedAsrModelSize,
                              )}
                            </p>
                            <p>
                              {m.importPage.environment.models.targetPathLabel(
                                resolvedModelStoragePath ?? startupCheck.speechModelStorageDir,
                              )}
                            </p>
                            <div className="download-progress__bar" aria-hidden="true">
                              <span
                                style={{
                                  width: `${Math.min(
                                    100,
                                    Math.max(0, downloadStatus.progress),
                                  )}%`,
                                }}
                              />
                            </div>
                            <p>{downloadStatus.message}</p>
                          </div>
                        ) : null}

                        {!downloadStatus?.active && downloadStatus?.status === 'done' ? (
                          <div className="success-banner" role="status">
                            <strong>{downloadStatus.message}</strong>
                            <p>
                              {m.importPage.environment.models.verifiedStorageHint(
                                downloadStatus.targetPath ?? startupCheck.speechModelStorageDir,
                              )}
                            </p>
                          </div>
                        ) : null}

                        {!downloadStatus?.active && downloadStatus?.status === 'error' ? (
                          <div className="error-banner" role="alert">
                            <strong>{downloadStatus.message}</strong>
                            <p>
                              {downloadStatus.error ?? m.importPage.environment.models.downloadFailed}
                            </p>
                          </div>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                </>
              ) : null}

              {startupCheckError ? (
                <div className="error-banner" role="alert">
                  <strong>{m.common.misc.startupCheckFailed}</strong>
                  <p>{startupCheckError}</p>
                </div>
              ) : null}

              <div className="inline-actions">
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={onReloadStartupCheck}
                  disabled={isStartupCheckLoading}
                >
                  {isStartupCheckLoading
                    ? m.common.misc.loading
                    : m.common.buttons.reloadStartupCheck}
                </button>
              </div>
            </section>

            <section className="import-details__section">
              <h3>{language === 'zh' ? '开发排错信息' : 'Developer diagnostics'}</h3>
              {backendPayload ? (
                <pre className="json-preview">{backendPayload}</pre>
              ) : (
                <p className="helper-text">{m.importPage.workflowWaitingDescription}</p>
              )}
            </section>
          </div>
          </details>
        </form>
      </SectionCard>

      <SectionCard
        eyebrow={language === 'zh' ? '最近任务' : 'Recent tasks'}
        title={language === 'zh' ? '回看、重试与再次导出' : 'Review, retry, and export again'}
        description={
          language === 'zh'
            ? '最近处理过的任务会保存在本地，方便测试时快速回看结果、重试失败任务，或再次导出。'
            : 'Recent tasks stay on disk so testers can quickly reopen results, retry failures, or export again.'
        }
        className="span-12 import-secondary-section"
      >
        <RecentTasksPanel
          tasks={safeRecentTasks}
          isLoading={isHistoryLoading}
          errorMessage={historyError}
          onOpenTask={onOpenRecentTask}
          onRetryTask={onRetryRecentTask}
          onExportAgain={onExportRecentTask}
          onOpenExportFolder={onOpenTaskExportFolder}
        />
      </SectionCard>

      {isDownloadDialogOpen && startupCheck ? (
        <div className="modal-backdrop" role="presentation">
          <div
            className="modal-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-download-dialog-title"
          >
            <div className="modal-panel__head">
              <div>
                <h3 id="model-download-dialog-title">
                  {m.importPage.environment.models.dialogTitle}
                </h3>
                <p>{m.importPage.environment.models.dialogDescription}</p>
              </div>
            </div>

            <div className="storage-choice">
              <label className="storage-choice__option">
                <input
                  type="radio"
                  name="model-storage-mode"
                  checked={storageMode === 'default'}
                  onChange={() => setStorageMode('default')}
                />
                <div>
                  <strong>{m.importPage.environment.models.useDefaultStorage}</strong>
                  <p>{startupCheck.defaultSpeechModelStorageDir}</p>
                </div>
              </label>

              <label className="storage-choice__option">
                <input
                  type="radio"
                  name="model-storage-mode"
                  checked={storageMode === 'custom'}
                  onChange={() => setStorageMode('custom')}
                />
                <div>
                  <strong>{m.importPage.environment.models.useCustomStorage}</strong>
                  <p>
                    {safeTrim(customStoragePath) ||
                      m.importPage.environment.models.customStorageDescription}
                  </p>
                </div>
              </label>
            </div>

            <label className="field-block">
              <span className="field-label">
                {m.importPage.environment.models.customPathLabel}
              </span>
              <div className="input-row">
                <input
                  className="text-input"
                  type="text"
                  value={customStoragePath}
                  onChange={(event) => setCustomStoragePath(event.target.value)}
                  placeholder={m.importPage.environment.models.customPathPlaceholder}
                  disabled={storageMode !== 'custom'}
                  spellCheck={false}
                />
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={handlePickDirectory}
                  disabled={storageMode !== 'custom' || isPickingDirectory}
                >
                  {isPickingDirectory
                    ? m.common.misc.loading
                    : m.importPage.environment.models.browseFolder}
                </button>
              </div>
            </label>

            <div className="info-panel">
              <strong>
                {m.importPage.environment.models.downloadModelName(selectedAsrModelSize)}
              </strong>
              <p>
                {m.importPage.environment.models.targetPathLabel(
                  storageMode === 'default'
                    ? startupCheck.defaultSpeechModelStorageDir
                    : getOwnedModelRootPreview(customStoragePath) ||
                        startupCheck.speechModelStorageDir,
                )}
              </p>
            </div>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={rememberStoragePath}
                onChange={(event) => setRememberStoragePath(event.target.checked)}
              />
              <span>{m.importPage.environment.models.rememberStoragePath}</span>
            </label>

            {downloadDialogError ? (
              <div className="error-banner" role="alert">
                <strong>{m.importPage.environment.models.downloadFailed}</strong>
                <p>{downloadDialogError}</p>
              </div>
            ) : null}

            <div className="modal-panel__actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={() => setIsDownloadDialogOpen(false)}
                disabled={isModelDownloadStarting}
              >
                {m.importPage.environment.models.cancel}
              </button>
              <button
                type="button"
                className="button button--primary"
                onClick={handleConfirmDownload}
                disabled={isModelDownloadStarting}
              >
                {isModelDownloadStarting
                  ? m.common.buttons.downloadingModel
                  : m.importPage.environment.models.confirmDownload}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
