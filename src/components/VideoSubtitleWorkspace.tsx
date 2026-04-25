import { useMemo, useState, type FormEvent } from 'react'

import { useI18n } from '../i18n/useI18n'
import type { StartupCheckReport } from '../types/environment'
import type { AppConfig, ProviderName, TranscriptionProviderName } from '../types/models'
import type { VideoSubtitleDraft } from '../types/videoSubtitle'
import {
  hasUsableSpeechConfig,
  hasUsableTranslationConfig,
  isLocalSpeechProvider,
  safeTrim,
} from '../utils/config'
import { SectionCard } from './SectionCard'

type VideoSubtitleWorkspaceProps = {
  draft: VideoSubtitleDraft
  config: AppConfig | null
  startupCheck: StartupCheckReport | null
  isStartupCheckLoading: boolean
  isWorking: boolean
  processError: string | null
  onDraftChange: (patch: Partial<VideoSubtitleDraft>) => void
  onOpenSettings: () => void
  onStart: () => Promise<void> | void
}

type Language = 'zh' | 'en'

type ReadinessItem = {
  key: string
  label: string
  ready: boolean
  description: string
  nextStep?: string
}

type PipelineCopy = {
  title: string
  description: string
  successNote: string
}

type FriendlyError = {
  title: string
  nextStep: string
  detail?: string
}

type StatusCopy = {
  title: string
  description: string
  nextStep?: string
}

function getSpeechProviderLabel(
  provider: TranscriptionProviderName | null | undefined,
  language: Language,
): string {
  if (!provider) {
    return language === 'zh' ? '未配置' : 'Not configured'
  }

  const zhLabels: Record<string, string> = {
    baidu_realtime: '百度实时识别',
    tencent_realtime: '腾讯实时识别',
    openaiSpeech: 'OpenAI 兼容语音识别',
    localFasterWhisper: '本地 faster-whisper',
    baidu_file_async: '百度异步文件转写',
    tencent_file_async: '腾讯文件转写',
    xfyun_lfasr: '讯飞 LFASR',
    xfyun_speed_transcription: '讯飞极速转写',
  }

  const enLabels: Record<string, string> = {
    baidu_realtime: 'Baidu realtime ASR',
    tencent_realtime: 'Tencent realtime ASR',
    openaiSpeech: 'OpenAI-compatible speech',
    localFasterWhisper: 'Local faster-whisper',
    baidu_file_async: 'Baidu file async ASR',
    tencent_file_async: 'Tencent file ASR',
    xfyun_lfasr: 'iFlytek LFASR',
    xfyun_speed_transcription: 'iFlytek speed transcription',
  }

  return (language === 'zh' ? zhLabels : enLabels)[provider] ?? provider
}

function getTranslationProviderLabel(
  provider: ProviderName | null | undefined,
  language: Language,
): string {
  if (!provider) {
    return language === 'zh' ? '未配置' : 'Not configured'
  }

  if (provider === 'deepseek') {
    return 'DeepSeek'
  }

  return language === 'zh' ? 'OpenAI 兼容接口' : 'OpenAI-compatible API'
}

function getReadyText(ready: boolean, language: Language): string {
  if (language === 'zh') {
    return ready ? '已就绪' : '未就绪'
  }
  return ready ? 'Ready' : 'Not ready'
}

function buildPipelineCopy({
  language,
  isChineseSingle,
  isEnglishBilingual,
  usingImportedSubtitle,
}: {
  language: Language
  isChineseSingle: boolean
  isEnglishBilingual: boolean
  usingImportedSubtitle: boolean
}): PipelineCopy {
  if (language === 'zh') {
    if (isChineseSingle) {
      return {
        title: '中文视频 -> 中文字幕',
        description: '先识别中文语音，再直接生成与语音时间轴对齐的中文字幕。',
        successNote: '成功后会自动进入 Preview，你可以继续检查字幕内容并导出。',
      }
    }

    if (isEnglishBilingual && usingImportedSubtitle) {
      return {
        title: '英语视频 + 英文 SRT -> 第一版重对齐后中英字幕',
        description:
          '先读取英文 SRT，再参考英语语音时间轴做第一版句段级重对齐，最后生成中文字幕。',
        successNote: '成功后会自动进入 Preview，你可以继续检查双语字幕和导出结果。',
      }
    }

    if (isEnglishBilingual) {
      return {
        title: '英语视频 -> 中英字幕',
        description: '先识别英语语音，再调用现有翻译链路生成中英字幕。',
        successNote: '成功后会自动进入 Preview，你可以继续检查双语字幕和导出结果。',
      }
    }

    return {
      title: '当前组合暂不支持',
      description: '当前只允许 中文 + 单语，或 英语 + 双语。',
      successNote: '请先改成支持的组合后再开始测试。',
    }
  }

  if (isChineseSingle) {
    return {
      title: 'Chinese Video -> Chinese Subtitle',
      description: 'Transcribe Chinese speech first, then generate Chinese subtitles aligned to speech timing.',
      successNote: 'A successful run will jump to Preview so you can review and export.',
    }
  }

  if (isEnglishBilingual && usingImportedSubtitle) {
    return {
      title: 'English Video + English SRT -> Bilingual Subtitle After First-step Alignment',
      description:
        'Read the English SRT first, use English speech timing for first-step segment alignment, then generate Chinese translations.',
      successNote: 'A successful run will jump to Preview so you can review and export.',
    }
  }

  if (isEnglishBilingual) {
    return {
      title: 'English Video -> Bilingual Subtitle',
      description: 'Transcribe English speech first, then reuse the existing translation flow for bilingual subtitles.',
      successNote: 'A successful run will jump to Preview so you can review and export.',
    }
  }

  return {
    title: 'Current combination is not supported',
    description: 'Only Chinese + single-language output or English + bilingual output is allowed right now.',
    successNote: 'Switch to a supported combination before starting.',
  }
}

function buildFriendlyError(rawError: string, language: Language): FriendlyError {
  const trimmed = rawError.trim()
  const detail = language === 'zh' ? `原始信息：${trimmed}` : `Raw detail: ${trimmed}`

  if (language === 'zh') {
    if (
      trimmed.includes('视频文件路径不能为空') ||
      trimmed.includes('请先填写视频文件路径')
    ) {
      return {
        title: '当前问题：还没有填写视频文件路径。',
        nextStep: '下一步：填写本机绝对路径，例如 D:\\media\\demo.mp4。',
      }
    }

    if (trimmed.includes('视频文件不存在') || trimmed.includes('所选路径不是文件')) {
      return {
        title: '当前问题：视频路径无效，应用找不到这个文件。',
        nextStep: '下一步：检查文件是否存在，并填写本机绝对路径。',
        detail,
      }
    }

    if (
      trimmed.includes('英文字幕') &&
      (trimmed.includes('.srt') || trimmed.includes('SRT'))
    ) {
      return {
        title: '当前问题：英文字幕文件不符合要求。',
        nextStep: '下一步：只填写英文 .srt 文件；如果不测导入字幕分支，也可以把这个输入框留空。',
        detail,
      }
    }

    if (
      trimmed.includes('媒体工作流未就绪') ||
      trimmed.includes('FFmpeg') ||
      trimmed.includes('faster-whisper')
    ) {
      return {
        title: '当前问题：识别环境还没准备好。',
        nextStep: '下一步：打开设置页，先确认 FFmpeg、本地识别运行时和模型可用。',
        detail,
      }
    }

    if (trimmed.includes('识别配置不可用') || trimmed.includes('识别配置不完整')) {
      return {
        title: '当前问题：识别 provider 配置还不完整。',
        nextStep: '下一步：打开设置页，补全当前识别 provider 需要的鉴权和模型参数。',
        detail,
      }
    }

    if (trimmed.includes('翻译配置不完整') || trimmed.includes('翻译 provider 配置')) {
      return {
        title: '当前问题：翻译配置还不完整。',
        nextStep: '下一步：打开设置页，补全翻译 API Key、服务地址和模型。',
        detail,
      }
    }

    if (trimmed.includes('只支持 中文 + 单语') || trimmed.includes('只支持三种链路')) {
      return {
        title: '当前问题：当前组合不受支持。',
        nextStep: '下一步：改为 中文 + 单语，或 英语 + 双语；英语双语下可选英文 SRT。',
        detail,
      }
    }

    return {
      title: '当前问题：这次处理没有成功。',
      nextStep: '下一步：先检查路径和设置；如果仍失败，再根据原始信息继续排查。',
      detail,
    }
  }

  return {
    title: 'Current issue: this run did not finish successfully.',
    nextStep: 'Next step: check the file paths and settings first, then review the raw detail if needed.',
    detail,
  }
}

export function VideoSubtitleWorkspace({
  draft,
  config,
  startupCheck,
  isStartupCheckLoading,
  isWorking,
  processError,
  onDraftChange,
  onOpenSettings,
  onStart,
}: VideoSubtitleWorkspaceProps) {
  const { language } = useI18n()
  const languageKey: Language = language === 'zh' ? 'zh' : 'en'
  const [localError, setLocalError] = useState<string | null>(null)

  const normalizedVideoPath = safeTrim(draft.videoPath)
  const normalizedSubtitlePath = safeTrim(draft.subtitlePath)
  const isChineseSingle =
    draft.sourceLanguage === 'zh' && draft.outputMode === 'single'
  const isEnglishBilingual =
    draft.sourceLanguage === 'en' && draft.outputMode === 'bilingual'
  const usingImportedSubtitle = isEnglishBilingual && normalizedSubtitlePath.length > 0
  const selectionSupported = isChineseSingle || isEnglishBilingual

  const provider = config?.defaultTranscriptionProvider ?? null
  const usingLocalProvider = provider ? isLocalSpeechProvider(provider) : false
  const backendReady = !isStartupCheckLoading && Boolean(startupCheck?.backendReachable)
  const speechConfigReady = Boolean(
    config &&
      hasUsableSpeechConfig(config) &&
      (usingLocalProvider ? startupCheck?.readyForLocalTranscription ?? false : true),
  )
  const mediaWorkflowReady = usingLocalProvider
    ? startupCheck?.readyForMediaWorkflow ?? false
    : Boolean(config && hasUsableSpeechConfig(config))
  const recognitionReady = speechConfigReady && mediaWorkflowReady
  const translationNeeded = isEnglishBilingual
  const translationConfigReady = !translationNeeded || hasUsableTranslationConfig(config)
  const combinedError = localError ?? processError
  const canStart =
    backendReady &&
    Boolean(normalizedVideoPath) &&
    selectionSupported &&
    Boolean(config) &&
    !isStartupCheckLoading &&
    !isWorking &&
    recognitionReady &&
    translationConfigReady

  const pipelineCopy = useMemo(
    () =>
      buildPipelineCopy({
        language: languageKey,
        isChineseSingle,
        isEnglishBilingual,
        usingImportedSubtitle,
      }),
    [isChineseSingle, isEnglishBilingual, languageKey, usingImportedSubtitle],
  )

  const readinessItems = useMemo<ReadinessItem[]>(() => {
    if (languageKey === 'zh') {
      return [
        {
          key: 'backend',
          label: '后端/应用环境可用',
          ready: backendReady,
          description: backendReady
            ? '应用已经完成环境检查，可以正常开始视频字幕流程。'
            : isStartupCheckLoading
              ? '正在检测当前应用环境，请稍候。'
              : '应用环境还没准备好，当前还不能开始测试。',
          nextStep: backendReady
            ? undefined
            : '下一步：等待页面完成检测；如果一直未就绪，关闭后重新打开应用再试。',
        },
        {
          key: 'recognition',
          label: '识别环境可用',
          ready: recognitionReady,
          description: recognitionReady
            ? usingLocalProvider
              ? '本地识别环境已经就绪，可以读取视频并开始识别。'
              : '当前云端识别配置可用，可以开始识别。'
            : usingLocalProvider
              ? '本地识别环境还没准备好。'
              : '当前识别 provider 配置还不完整。',
          nextStep: recognitionReady
            ? undefined
            : usingLocalProvider
              ? '下一步：打开设置页，确认 FFmpeg、本地运行时和模型都可用。'
              : '下一步：打开设置页，补全当前识别 provider 的鉴权和模型参数。',
        },
        {
          key: 'translation',
          label: '翻译配置可用',
          ready: translationConfigReady,
          description: translationNeeded
            ? translationConfigReady
              ? '当前翻译配置已经就绪，英语双语链路可以继续生成中文字幕。'
              : '英语双语链路需要翻译配置，但现在还没准备好。'
            : '当前是中文字幕链路，这一步不需要额外翻译配置。',
          nextStep:
            translationNeeded && !translationConfigReady
              ? '下一步：打开设置页，补全翻译 API Key、服务地址和模型。'
              : undefined,
        },
        {
          key: 'selection',
          label: '当前组合可执行',
          ready: selectionSupported,
          description: selectionSupported
            ? `当前会走：${pipelineCopy.title}`
            : '当前组合不在本阶段支持范围内。',
          nextStep: selectionSupported
            ? undefined
            : '下一步：改为 中文 + 单语，或 英语 + 双语。',
        },
      ]
    }

    return [
      {
        key: 'backend',
        label: 'App environment',
        ready: backendReady,
        description: backendReady
          ? 'Environment check is ready.'
          : isStartupCheckLoading
            ? 'Environment check is still running.'
            : 'The app environment is not ready yet.',
        nextStep: backendReady ? undefined : 'Next step: wait for the check to finish or restart the app.',
      },
      {
        key: 'recognition',
        label: 'Speech setup',
        ready: recognitionReady,
        description: recognitionReady
          ? 'Speech recognition can start.'
          : 'Speech recognition is not ready yet.',
        nextStep: recognitionReady ? undefined : 'Next step: open Settings and fix the speech environment.',
      },
      {
        key: 'translation',
        label: 'Translation setup',
        ready: translationConfigReady,
        description: translationNeeded
          ? translationConfigReady
            ? 'Translation is ready for bilingual output.'
            : 'Translation config is still missing.'
          : 'Translation is not needed for this selection.',
        nextStep:
          translationNeeded && !translationConfigReady
            ? 'Next step: open Settings and complete translation config.'
            : undefined,
      },
      {
        key: 'selection',
        label: 'Current combination',
        ready: selectionSupported,
        description: selectionSupported
          ? `Current path: ${pipelineCopy.title}`
          : 'Current combination is not supported.',
        nextStep: selectionSupported ? undefined : 'Next step: switch to a supported combination.',
      },
    ]
  }, [
    backendReady,
    isStartupCheckLoading,
    languageKey,
    pipelineCopy.title,
    recognitionReady,
    selectionSupported,
    translationConfigReady,
    translationNeeded,
    usingLocalProvider,
  ])

  const currentStatus = useMemo<StatusCopy>(() => {
    if (languageKey === 'zh') {
      if (isWorking) {
        return {
          title: '当前状态：正在处理中',
          description: `LinguaSub 正在执行“${pipelineCopy.title}”。`,
          nextStep: '完成后会自动进入 Preview，你可以继续检查字幕和导出。',
        }
      }

      if (!backendReady) {
        return {
          title: '当前状态：还不能开始测试',
          description: '应用环境还没确认完成。',
          nextStep: '下一步：先看顶部就绪状态区，等待“后端/应用环境可用”变成“已就绪”。',
        }
      }

      if (!normalizedVideoPath) {
        return {
          title: '当前状态：还不能开始测试',
          description: '还没有填写视频文件路径。',
          nextStep: '下一步：填写本机绝对路径，例如 D:\\media\\demo.mp4。',
        }
      }

      if (!selectionSupported) {
        return {
          title: '当前状态：还不能开始测试',
          description: '当前组合不受支持。',
          nextStep: '下一步：改为 中文 + 单语，或 英语 + 双语。',
        }
      }

      if (!recognitionReady) {
        return {
          title: '当前状态：还不能开始测试',
          description: '识别环境还没准备好。',
          nextStep: usingLocalProvider
            ? '下一步：打开设置页，确认 FFmpeg、本地识别运行时和模型已就绪。'
            : '下一步：打开设置页，补全识别 provider 需要的参数。',
        }
      }

      if (!translationConfigReady) {
        return {
          title: '当前状态：还不能开始测试',
          description: '当前英语双语链路需要翻译配置，但现在还没准备好。',
          nextStep: '下一步：打开设置页，补全翻译 API Key、服务地址和模型。',
        }
      }

      return {
        title: '当前状态：现在可以开始测试',
        description: `本次会走“${pipelineCopy.title}”。`,
        nextStep: pipelineCopy.successNote,
      }
    }

    if (isWorking) {
      return {
        title: 'Status: processing',
        description: `LinguaSub is running “${pipelineCopy.title}”.`,
        nextStep: 'It will jump to Preview automatically when finished.',
      }
    }

    if (!canStart) {
      return {
        title: 'Status: not ready yet',
        description: 'The current input or setup is not ready.',
        nextStep: 'Check the readiness section above and fix the first item that is still not ready.',
      }
    }

    return {
      title: 'Status: ready to test',
      description: `Current path: ${pipelineCopy.title}.`,
      nextStep: pipelineCopy.successNote,
    }
  }, [
    backendReady,
    canStart,
    isWorking,
    languageKey,
    normalizedVideoPath,
    pipelineCopy.successNote,
    pipelineCopy.title,
    recognitionReady,
    selectionSupported,
    translationConfigReady,
    usingLocalProvider,
  ])

  const friendlyError = useMemo(
    () => (combinedError ? buildFriendlyError(combinedError, languageKey) : null),
    [combinedError, languageKey],
  )

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLocalError(null)

    if (!normalizedVideoPath) {
      setLocalError(
        languageKey === 'zh'
          ? '请先填写视频文件路径。'
          : 'Please fill in the video file path first.',
      )
      return
    }

    if (!selectionSupported) {
      setLocalError(
        languageKey === 'zh'
          ? '当前只支持 中文 + 单语，或 英语 + 双语。'
          : 'Only Chinese + single-language output or English + bilingual output is supported.',
      )
      return
    }

    if (usingImportedSubtitle && !normalizedSubtitlePath.toLowerCase().endsWith('.srt')) {
      setLocalError(
        languageKey === 'zh'
          ? '英文字幕文件当前只支持 .srt。'
          : 'Only .srt is supported for imported English subtitles.',
      )
      return
    }

    void onStart()
  }

  return (
    <SectionCard
      eyebrow={languageKey === 'zh' ? '视频字幕' : 'Video Subtitle'}
      title={languageKey === 'zh' ? '准备生成字幕' : 'Prepare subtitle generation'}
      description={pipelineCopy.description}
      className="span-12 video-subtitle-workspace"
    >
      <form className="video-subtitle-form" onSubmit={handleSubmit}>
        <div className="video-subtitle-layout">
          <div className="video-subtitle-layout__primary">
        <div className="video-subtitle-primary-grid">
          <label className="field-block video-subtitle-path-field">
            <span className="field-label">
              {languageKey === 'zh' ? '视频文件路径' : 'Video file path'}
            </span>
            <input
              className="text-input"
              type="text"
              value={draft.videoPath}
              onChange={(event) => {
                setLocalError(null)
                onDraftChange({ videoPath: event.target.value })
              }}
              placeholder="D:\media\demo.mp4"
              spellCheck={false}
              disabled={isWorking}
            />
            <p className="helper-text">
              {languageKey === 'zh'
                ? '请填写本机绝对路径，例如 D:\\media\\demo.mp4。'
                : 'Use a local absolute path such as D:\\media\\demo.mp4.'}
            </p>
          </label>

          <label className="field-block">
            <span className="field-label">
              {languageKey === 'zh' ? '源语言' : 'Source language'}
            </span>
            <select
              className="select-input"
              value={draft.sourceLanguage}
              disabled={isWorking}
              onChange={(event) => {
                const nextLanguage = event.target.value as VideoSubtitleDraft['sourceLanguage']
                setLocalError(null)
                onDraftChange({
                  sourceLanguage: nextLanguage,
                  outputMode: nextLanguage === 'zh' ? 'single' : 'bilingual',
                  subtitlePath: nextLanguage === 'zh' ? '' : draft.subtitlePath,
                })
              }}
            >
              <option value="zh">{languageKey === 'zh' ? '中文' : 'Chinese'}</option>
              <option value="en">{languageKey === 'zh' ? '英语' : 'English'}</option>
            </select>
          </label>

          <label className="field-block">
            <span className="field-label">
              {languageKey === 'zh' ? '输出模式' : 'Output mode'}
            </span>
            <select
              className="select-input"
              value={draft.outputMode}
              disabled={isWorking}
              onChange={(event) => {
                const nextMode = event.target.value as VideoSubtitleDraft['outputMode']
                setLocalError(null)
                onDraftChange({
                  outputMode: nextMode,
                  sourceLanguage: nextMode === 'single' ? 'zh' : 'en',
                  subtitlePath: nextMode === 'single' ? '' : draft.subtitlePath,
                })
              }}
            >
              <option value="single" disabled={draft.sourceLanguage !== 'zh'}>
                {languageKey === 'zh' ? '单语（中文）' : 'Single-language (Chinese)'}
              </option>
              <option value="bilingual" disabled={draft.sourceLanguage !== 'en'}>
                {languageKey === 'zh' ? '双语（英语）' : 'Bilingual (English)'}
              </option>
            </select>
          </label>
        </div>

        {isEnglishBilingual ? (
          <label className="field-block video-subtitle-subtitle-field">
            <span className="field-label">
              {languageKey === 'zh'
                ? '英文字幕文件（可选，仅 .srt）'
                : 'English subtitle file (optional, .srt only)'}
            </span>
            <input
              className="text-input"
              type="text"
              value={draft.subtitlePath}
              onChange={(event) => {
                setLocalError(null)
                onDraftChange({ subtitlePath: event.target.value })
              }}
              placeholder="D:\subtitle\demo.en.srt"
              spellCheck={false}
              disabled={isWorking}
            />
            <p className="helper-text">
              {languageKey === 'zh'
                ? '留空会直接生成中英字幕；填写英文 SRT 后会参考英语语音时间轴做第一版重对齐。'
                : 'Leave it empty for normal bilingual subtitles, or provide an English SRT for first-step alignment.'}
            </p>
          </label>
        ) : null}

        <div className="video-subtitle-action-row">
          <div className="video-subtitle-action-copy">
            <strong>{pipelineCopy.title}</strong>
            <span>
              {languageKey === 'zh'
                ? '生成完成后会自动进入预览，你可以继续检查和导出。'
                : 'A successful run will jump to Preview so you can review and export.'}
            </span>
          </div>
          <div className="video-subtitle-actions">
            <button
              type="button"
              className="button button--ghost"
              onClick={onOpenSettings}
              disabled={isWorking}
            >
              {languageKey === 'zh' ? '打开设置' : 'Open settings'}
            </button>
            <button
              type="submit"
              className="button button--primary video-subtitle-primary-button"
              disabled={!canStart}
            >
              {isWorking
                ? languageKey === 'zh'
                  ? '正在生成字幕...'
                  : 'Generating subtitles...'
                : languageKey === 'zh'
                  ? '开始生成字幕'
                  : 'Start subtitle generation'}
            </button>
          </div>
        </div>
          </div>

          <div className="video-subtitle-layout__aside">
            <div
              className="video-subtitle-status-row"
              aria-label={languageKey === 'zh' ? '当前状态' : 'Current status'}
            >
              {readinessItems.map((item) => (
                <span
                  key={item.key}
                  className={`status-chip ${item.ready ? 'status-chip--ready' : 'status-chip--blocked'}`}
                  title={`${item.description}${item.nextStep ? ` ${item.nextStep}` : ''}`}
                >
                  <span>{item.label}</span>
                  <strong>{getReadyText(item.ready, languageKey)}</strong>
                </span>
              ))}
            </div>

            <div className="video-subtitle-callout">
              {friendlyError ? (
                <div className="warning-banner video-subtitle-message" role="alert">
                  <strong>{friendlyError.title}</strong>
                  <p>{friendlyError.nextStep}</p>
                  {friendlyError.detail ? <p>{friendlyError.detail}</p> : null}
                </div>
              ) : (
                <div className="info-panel video-subtitle-message">
                  <strong>{currentStatus.title}</strong>
                  <p>{currentStatus.description}</p>
                  {currentStatus.nextStep ? <p>{currentStatus.nextStep}</p> : null}
                </div>
              )}
            </div>
          </div>
        </div>
      </form>

      <details className="video-subtitle-details">
        <summary>
          {languageKey === 'zh'
            ? '查看当前设置与支持范围'
            : 'View current settings and supported modes'}
        </summary>
        <div className="video-subtitle-details__grid">
          <div>
            <span className="field-label">
              {languageKey === 'zh' ? '识别服务商' : 'Speech provider'}
            </span>
            <strong>{getSpeechProviderLabel(provider, languageKey)}</strong>
            <p>{getReadyText(recognitionReady, languageKey)}</p>
          </div>
          <div>
            <span className="field-label">
              {languageKey === 'zh' ? '翻译服务商' : 'Translation provider'}
            </span>
            <strong>
              {translationNeeded && config
                ? getTranslationProviderLabel(config.defaultProvider, languageKey)
                : languageKey === 'zh'
                  ? '当前不需要'
                  : 'Not needed'}
            </strong>
            <p>
              {translationNeeded && config
                ? `${config.model} / ${config.baseUrl}`
                : getReadyText(translationConfigReady, languageKey)}
            </p>
          </div>
          <div>
            <span className="field-label">
              {languageKey === 'zh' ? '支持范围' : 'Supported modes'}
            </span>
            <strong>
              {languageKey === 'zh'
                ? '中文单语、英语双语'
                : 'Chinese single, English bilingual'}
            </strong>
            <p>
              {languageKey === 'zh'
                ? '英语双语可选英文 SRT。'
                : 'English bilingual output can optionally use an English SRT.'}
            </p>
          </div>
          <div>
            <span className="field-label">
              {languageKey === 'zh' ? '当前链路' : 'Current path'}
            </span>
            <strong>{pipelineCopy.title}</strong>
            <p>{pipelineCopy.description}</p>
          </div>
        </div>
      </details>
    </SectionCard>
  )
}
