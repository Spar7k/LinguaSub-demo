import { useState } from 'react'

import type { ExportFormat, ExportResult, WordExportMode } from '../types/export'
import { useI18n } from '../i18n/useI18n'
import type { ContentSummaryResult } from '../types/agent'
import type { ImportResult } from '../types/import'
import type { OutputMode, ProjectState } from '../types/models'
import type {
  VideoBurnExportMode,
  VideoBurnExportResult,
} from '../types/videoExport'
import { safeTrim } from '../utils/config'
import { SectionCard } from './SectionCard'

type ExportTarget =
  | 'subtitle'
  | 'recognitionText'
  | 'word'
  | 'contentSummaryWord'
  | 'video'

type ExportWorkspaceProps = {
  importResult: ImportResult | null
  projectState: ProjectState
  exportFormat: ExportFormat
  outputMode: OutputMode
  wordExportMode: WordExportMode
  exportFileName: string
  exportResult: ExportResult | null
  videoBurnMode: VideoBurnExportMode
  videoBurnExportResult: VideoBurnExportResult | null
  processError: string | null
  isExporting: boolean
  isVideoBurnExporting: boolean
  hasUnsavedChanges: boolean
  contentSummaryResult: ContentSummaryResult | null
  contentSummaryGeneratedAt: string | null
  isContentSummaryStale: boolean
  onOpenExportFolder: () => void
  onOpenVideoBurnExportFolder: () => void
  onExportFormatChange: (format: ExportFormat) => void
  onOutputModeChange: (mode: OutputMode) => void
  onWordExportModeChange: (mode: WordExportMode) => void
  onFileNameChange: (value: string) => void
  onVideoBurnModeChange: (mode: VideoBurnExportMode) => void
  onExportSubtitles: (format: ExportFormat) => void
  onExportBurnedVideo: () => void
  onExportContentSummaryWord: () => void
  onClearExportError: () => void
}

function getDefaultFileName(
  sourceFilePath: string | null,
  exportFormat: ExportFormat,
  outputMode: OutputMode,
  wordExportMode: WordExportMode,
): string {
  const sourceName = sourceFilePath
    ? sourceFilePath.split(/[\\/]/).pop()?.replace(/\.[^/.]+$/, '')
    : null
  const stem = sourceName || 'linguasub-subtitles'

  if (exportFormat === 'word') {
    if (wordExportMode === 'bilingualTable') {
      return `${stem}_bilingual.docx`
    }
    if (wordExportMode === 'transcript') {
      return `${stem}_transcript.docx`
    }
    return `${stem}.docx`
  }

  if (exportFormat === 'recognition_text') {
    return `${stem}.recognition.txt`
  }

  if (exportFormat === 'content_summary_word') {
    return `${stem}.content-summary.docx`
  }

  const suffix = outputMode === 'bilingual' ? 'bilingual' : 'single'
  return `${stem}.${suffix}.srt`
}

function getDirectoryLabel(sourceFilePath: string | null): string {
  if (!sourceFilePath) {
    return ''
  }

  const separatorIndex = Math.max(
    sourceFilePath.lastIndexOf('\\'),
    sourceFilePath.lastIndexOf('/'),
  )
  if (separatorIndex < 0) {
    return ''
  }

  return sourceFilePath.slice(0, separatorIndex)
}

function getInitialExportTarget(exportFormat: ExportFormat): ExportTarget {
  if (exportFormat === 'word') {
    return 'word'
  }

  if (exportFormat === 'recognition_text') {
    return 'recognitionText'
  }

  if (exportFormat === 'content_summary_word') {
    return 'contentSummaryWord'
  }

  return 'subtitle'
}

function getExportTargetFormat(target: ExportTarget): ExportFormat {
  if (target === 'word') {
    return 'word'
  }

  if (target === 'recognitionText') {
    return 'recognition_text'
  }

  if (target === 'contentSummaryWord') {
    return 'content_summary_word'
  }

  return 'srt'
}

const exportTargets: ExportTarget[] = [
  'subtitle',
  'recognitionText',
  'word',
  'contentSummaryWord',
  'video',
]

function formatGeneratedAt(value: string | null, language: string): string | null {
  if (!value) {
    return null
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return null
  }

  return new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : 'en', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

export function ExportWorkspace({
  importResult,
  projectState,
  exportFormat,
  outputMode,
  wordExportMode,
  exportFileName,
  exportResult,
  videoBurnMode,
  videoBurnExportResult,
  processError,
  isExporting,
  isVideoBurnExporting,
  hasUnsavedChanges,
  contentSummaryResult,
  contentSummaryGeneratedAt,
  isContentSummaryStale,
  onOpenExportFolder,
  onOpenVideoBurnExportFolder,
  onExportFormatChange,
  onOutputModeChange,
  onWordExportModeChange,
  onFileNameChange,
  onVideoBurnModeChange,
  onExportSubtitles,
  onExportBurnedVideo,
  onExportContentSummaryWord,
  onClearExportError,
}: ExportWorkspaceProps) {
  const { m, language } = useI18n()
  const [exportTarget, setExportTarget] = useState<ExportTarget>(() =>
    getInitialExportTarget(exportFormat),
  )
  const copy = m.exportPage.task
  const resultNoteCopy =
    language === 'zh'
      ? {
          conflictResolved: '检测到同名文件，已自动追加序号保存。',
          sanitized: '文件名中的非法字符已自动清洗。',
        }
      : {
          conflictResolved:
            'LinguaSub found an existing file with the same name and saved this export with an added number.',
          sanitized:
            'Unsupported characters were removed from the requested file name automatically.',
        }

  const translatedCount = projectState.segments.filter((segment) =>
    safeTrim(segment.translatedText),
  ).length
  const missingTranslationCount = projectState.segments.filter(
    (segment) => !safeTrim(segment.translatedText),
  ).length
  const invalidTimelineCount = projectState.segments.filter(
    (segment) =>
      !Number.isFinite(segment.start) ||
      !Number.isFinite(segment.end) ||
      segment.start < 0 ||
      segment.end < segment.start,
  ).length
  const currentFilePath = importResult?.currentFile.path ?? null
  const currentVideoPath =
    importResult?.currentFile.mediaType === 'video'
      ? importResult.currentFile.path
      : projectState.currentFile?.mediaType === 'video'
        ? projectState.currentFile.path
        : null
  const currentVideoName =
    importResult?.currentFile.mediaType === 'video'
      ? importResult.currentFile.name
      : projectState.currentFile?.mediaType === 'video'
        ? projectState.currentFile.name
        : null
  const isBusy = isExporting || isVideoBurnExporting
  const hasRecognitionText = projectState.segments.some((segment) =>
    safeTrim(segment.sourceText),
  )
  const canExportFile = projectState.segments.length > 0 && !isBusy
  const canExportRecognitionText =
    projectState.segments.length > 0 && hasRecognitionText && !isBusy
  const canExportContentSummaryWord =
    Boolean(contentSummaryResult) && !isContentSummaryStale && !isBusy
  const canExportBurnedVideo =
    Boolean(currentVideoPath) && projectState.segments.length > 0 && !isBusy
  const contentSummaryGeneratedAtLabel = formatGeneratedAt(
    contentSummaryGeneratedAt,
    language,
  )
  const contentSummaryStatus = !contentSummaryResult
    ? copy.contentSummaryStatus.missing
    : isContentSummaryStale
      ? copy.contentSummaryStatus.stale
      : copy.contentSummaryStatus.ready
  const activeFormat = getExportTargetFormat(exportTarget)
  const effectiveFileName =
    safeTrim(exportFileName) ||
    getDefaultFileName(currentFilePath, activeFormat, outputMode, wordExportMode)
  const destinationDirectory =
    getDirectoryLabel(currentFilePath) || m.exportPage.currentProjectFolder
  const workflowLabel = importResult
    ? importResult.workflow
        .map((step) => m.common.workflowSteps[step as keyof typeof m.common.workflowSteps] ?? step)
        .join(' -> ')
    : ''
  const formatValue = m.exportPage.fileFormatValues[activeFormat]
  const formatDescription =
    exportTarget === 'word'
      ? m.exportPage.fileFormatDescriptions.word
      : exportTarget === 'recognitionText'
        ? m.exportPage.fileFormatDescriptions.recognition_text
        : exportTarget === 'contentSummaryWord'
          ? m.exportPage.fileFormatDescriptions.content_summary_word
          : m.exportPage.fileFormatDescriptions.srt
  const wordModeDescription =
    wordExportMode === 'transcript'
      ? m.exportPage.wordModeDescriptions.transcript
      : m.exportPage.wordModeDescriptions.bilingualTable
  const activeFileResult =
    exportResult &&
    ((exportTarget === 'subtitle' && exportResult.format === 'srt') ||
      (exportTarget === 'recognitionText' &&
        exportResult.format === 'recognition_text') ||
      (exportTarget === 'word' && exportResult.format === 'word') ||
      (exportTarget === 'contentSummaryWord' &&
        exportResult.format === 'content_summary_word'))
      ? exportResult
      : null
  const activeVideoResult = exportTarget === 'video' ? videoBurnExportResult : null
  const primaryDisabled =
    exportTarget === 'video'
      ? !canExportBurnedVideo
      : exportTarget === 'contentSummaryWord'
        ? !canExportContentSummaryWord
        : exportTarget === 'recognitionText'
          ? !canExportRecognitionText
          : !canExportFile
  const primaryLabel =
    exportTarget === 'video'
      ? isVideoBurnExporting
        ? copy.buttons.exportingVideo
        : copy.buttons.exportVideo
      : isExporting
        ? copy.buttons.exporting
        : exportTarget === 'contentSummaryWord'
          ? copy.buttons.exportContentSummaryWord
          : exportTarget === 'word'
            ? copy.buttons.exportWord
            : exportTarget === 'recognitionText'
              ? copy.buttons.exportRecognitionText
              : copy.buttons.exportSubtitle

  function selectExportTarget(nextTarget: ExportTarget) {
    setExportTarget(nextTarget)
    onClearExportError()
    if (nextTarget === 'subtitle') {
      onExportFormatChange('srt')
    }
    if (nextTarget === 'recognitionText') {
      onExportFormatChange('recognition_text')
    }
    if (nextTarget === 'word') {
      onExportFormatChange('word')
    }
    if (nextTarget === 'contentSummaryWord') {
      onExportFormatChange('content_summary_word')
    }
  }

  function handlePrimaryExport() {
    if (exportTarget === 'video') {
      onExportBurnedVideo()
      return
    }
    if (exportTarget === 'contentSummaryWord') {
      onExportContentSummaryWord()
      return
    }
    onExportSubtitles(getExportTargetFormat(exportTarget))
  }

  return (
    <SectionCard
      eyebrow={m.exportPage.sections.export.eyebrow}
      title={m.exportPage.sections.export.title}
      description={m.exportPage.sections.export.description}
      className="span-12 export-workspace-card"
    >
      <div className="export-layout">
        <div className="export-layout__primary">
      <div className="export-target-group">
        <span className="field-label">{copy.targetLabel}</span>
        <div className="export-target-grid" role="tablist" aria-label={copy.targetLabel}>
          {exportTargets.map((target) => (
            <button
              key={target}
              type="button"
              className={`export-target-card ${
                exportTarget === target ? 'export-target-card--active' : ''
              }`.trim()}
              onClick={() => selectExportTarget(target)}
              disabled={isBusy}
              aria-pressed={exportTarget === target}
            >
              <strong>{copy.targets[target].title}</strong>
              <span>{copy.targets[target].description}</span>
            </button>
          ))}
        </div>
      </div>

      {exportTarget !== 'video' ? (
        <div className="export-options-grid">
          {exportTarget === 'subtitle' ? (
            <label className="field-block">
              <span className="field-label">{m.common.summary.outputMode}</span>
              <select
                className="select-input"
                value={outputMode}
                onChange={(event) => onOutputModeChange(event.target.value as OutputMode)}
                disabled={isBusy}
              >
                <option value="bilingual">{m.common.outputModes.bilingual}</option>
                <option value="single">{m.common.outputModes.single}</option>
              </select>
            </label>
          ) : exportTarget === 'word' ? (
            <label className="field-block">
              <span className="field-label">{m.exportPage.wordModeLabel}</span>
              <select
                className="select-input"
                value={wordExportMode}
                onChange={(event) =>
                  onWordExportModeChange(event.target.value as WordExportMode)
                }
                disabled={isBusy}
              >
                <option value="bilingualTable">
                  {m.common.wordExportModes.bilingualTable}
                </option>
                <option value="transcript">{m.common.wordExportModes.transcript}</option>
              </select>
            </label>
          ) : null}

          <label
            className={`field-block export-file-name-field ${
              exportTarget === 'recognitionText' ||
              exportTarget === 'contentSummaryWord'
                ? 'export-file-name-field--wide'
                : ''
            }`.trim()}
          >
            <span className="field-label">{copy.fileNameLabel}</span>
            <input
              className="text-input"
              type="text"
              value={exportFileName}
              onChange={(event) => onFileNameChange(event.target.value)}
              placeholder={getDefaultFileName(
                currentFilePath,
                activeFormat,
                outputMode,
                wordExportMode,
              )}
              spellCheck={false}
              disabled={isBusy}
            />
            <span className="field-hint">{copy.fileNameHint}</span>
          </label>
        </div>
      ) : (
        <div className="export-video-panel">
          <label className="field-block">
            <span className="field-label">{m.common.summary.outputMode}</span>
            <select
              className="select-input"
              value={videoBurnMode}
              onChange={(event) =>
                onVideoBurnModeChange(event.target.value as VideoBurnExportMode)
              }
              disabled={isBusy}
            >
              <option value="bilingual">
                {language === 'zh' ? '双语字幕' : 'Bilingual subtitles'}
              </option>
              <option value="translated">
                {language === 'zh' ? '仅译文字幕' : 'Translated subtitles only'}
              </option>
            </select>
          </label>

          <div className="export-video-style">
            <span>{copy.videoStyleTitle}</span>
            <strong>{copy.videoStyleDescription}</strong>
          </div>

          <div className="export-source-summary">
            <span className="field-label">{copy.videoSourceLabel}</span>
            <strong>{currentVideoPath ? currentVideoName : m.common.misc.notSelected}</strong>
            <p>{currentVideoPath ? currentVideoPath : copy.noOriginalVideo}</p>
          </div>
        </div>
      )}

      <div className="export-primary-row">
        <div>
          <strong>
            {copy.targets[exportTarget].title}
          </strong>
          <p>
            {exportTarget === 'video'
              ? copy.outputRulesDescription
              : `${destinationDirectory} / ${effectiveFileName}`}
          </p>
        </div>
        <button
          type="button"
          className="button button--primary export-primary-button"
          onClick={handlePrimaryExport}
          disabled={primaryDisabled}
        >
          {primaryLabel}
        </button>
      </div>
        </div>

        <div className="export-layout__aside">
      <div className="export-summary-chips" aria-label={copy.projectSummaryTitle}>
        <span className="metric-chip">
          <span className="metric-chip__label">{m.common.summary.subtitleRows}</span>
          <strong>{projectState.segments.length}</strong>
        </span>
        <span className="metric-chip">
          <span className="metric-chip__label">{m.common.summary.translatedRows}</span>
          <strong>
            {translatedCount} / {projectState.segments.length}
          </strong>
        </span>
        <span className="metric-chip">
          <span className="metric-chip__label">{m.common.summary.livePreviewEdits}</span>
          <strong>
            {hasUnsavedChanges
              ? m.common.misc.includedInExport
              : m.common.misc.alreadySaved}
          </strong>
        </span>
      </div>

      {exportTarget === 'contentSummaryWord' ? (
        <div
          className={`export-content-summary-status export-content-summary-status--${contentSummaryStatus.tone}`}
        >
          <div>
            <span className="field-label">{copy.contentSummaryStatusLabel}</span>
            <strong>{contentSummaryStatus.title}</strong>
            <p>{contentSummaryStatus.description}</p>
          </div>
          <div className="export-content-summary-status__stats">
            <span>
              {copy.contentSummaryChaptersLabel}:{' '}
              <strong>{contentSummaryResult?.chapters.length ?? 0}</strong>
            </span>
            <span>
              {copy.contentSummaryKeywordsLabel}:{' '}
              <strong>{contentSummaryResult?.keywords.length ?? 0}</strong>
            </span>
            {contentSummaryGeneratedAtLabel ? (
              <span>
                {copy.contentSummaryGeneratedAtLabel}:{' '}
                <strong>{contentSummaryGeneratedAtLabel}</strong>
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {projectState.segments.length === 0 ? (
        <div className="error-banner" role="alert">
          <strong>{m.common.misc.noSubtitleContent}</strong>
          <p>
            {exportTarget === 'contentSummaryWord'
              ? copy.contentSummaryStatus.missing.description
              : exportTarget === 'recognitionText'
              ? m.app.errors.noRecognitionTextToExport
              : exportTarget === 'video'
                ? copy.noSegments
                : m.exportPage.noSubtitleDescription}
          </p>
        </div>
      ) : null}

      {exportTarget === 'recognitionText' &&
      projectState.segments.length > 0 &&
      !hasRecognitionText ? (
        <div className="error-banner" role="alert">
          <strong>{copy.targets.recognitionText.title}</strong>
          <p>{m.app.errors.noRecognitionTextToExport}</p>
        </div>
      ) : null}

      {exportTarget === 'subtitle' &&
      outputMode === 'bilingual' &&
      missingTranslationCount > 0 ? (
        <div className="warning-banner" role="alert">
          <strong>{m.common.misc.missingTranslatedLines}</strong>
          <p>{m.exportPage.missingLinesDescription(missingTranslationCount)}</p>
        </div>
      ) : null}

      {exportTarget === 'word' && missingTranslationCount > 0 ? (
        <div className="warning-banner" role="alert">
          <strong>{m.common.misc.missingTranslatedLines}</strong>
          <p>{m.exportPage.wordMissingTranslationsDescription(missingTranslationCount)}</p>
        </div>
      ) : null}

      {exportTarget === 'video' && !currentVideoPath ? (
        <div className="warning-banner" role="alert">
          <strong>{copy.videoSourceLabel}</strong>
          <p>{copy.noOriginalVideo}</p>
        </div>
      ) : null}

      {invalidTimelineCount > 0 &&
      exportTarget !== 'video' &&
      exportTarget !== 'contentSummaryWord' ? (
        <div
          className={exportTarget === 'word' ? 'warning-banner' : 'error-banner'}
          role="alert"
        >
          <strong>{m.common.misc.timelineNeedsAttention}</strong>
          <p>
            {exportTarget === 'word'
              ? m.exportPage.wordInvalidTimelineDescription(invalidTimelineCount)
              : m.exportPage.invalidTimelineDescription(invalidTimelineCount)}
          </p>
        </div>
      ) : null}

      {processError ? (
        <div className="export-result-strip export-result-strip--error" role="alert">
          <strong>{copy.failureTitle}</strong>
          <p>{processError}</p>
          <span>{copy.failureHint}</span>
        </div>
      ) : null}

      {activeFileResult ? (
        <div className="export-result-strip export-result-strip--success" role="status">
          <strong>{copy.successTitle}</strong>
          <p>{m.exportPage.lastExportDescription(activeFileResult.fileName)}</p>
          <span>{copy.outputPathLabel}</span>
          <code className="path-preview">{activeFileResult.path}</code>
          {activeFileResult.conflictResolved || activeFileResult.sanitizedFileName ? (
            <p>
              {activeFileResult.conflictResolved ? resultNoteCopy.conflictResolved : null}
              {activeFileResult.conflictResolved && activeFileResult.sanitizedFileName
                ? ' '
                : null}
              {activeFileResult.sanitizedFileName ? resultNoteCopy.sanitized : null}
            </p>
          ) : null}
          <button
            type="button"
            className="button button--secondary"
            onClick={onOpenExportFolder}
          >
            {copy.openFolder}
          </button>
        </div>
      ) : null}

      {activeVideoResult ? (
        <div className="export-result-strip export-result-strip--success" role="status">
          <strong>{copy.successTitle}</strong>
          <p>{activeVideoResult.message}</p>
          <span>{copy.outputPathLabel}</span>
          <code className="path-preview">{activeVideoResult.outputPath}</code>
          <button
            type="button"
            className="button button--secondary"
            onClick={onOpenVideoBurnExportFolder}
          >
            {copy.openFolder}
          </button>
        </div>
      ) : null}
        </div>
      </div>

      <details className="export-details">
        <summary>{copy.detailsTitle}</summary>
        <div className="export-details__grid">
          <div>
            <span className="field-label">{copy.projectSummaryTitle}</span>
            {importResult ? (
              <>
                <strong>{importResult.currentFile.name}</strong>
                <p>
                  {m.common.summary.route}: {workflowLabel || m.common.misc.notRecorded}
                </p>
                <p>
                  {m.common.summary.projectStatus}: {m.common.statuses[projectState.status]}
                </p>
              </>
            ) : (
              <p>{m.exportPage.noProjectDescription}</p>
            )}
          </div>

          <div>
            <span className="field-label">{copy.formatDetailsTitle}</span>
            <strong>{exportTarget === 'video' ? copy.targets.video.title : formatValue}</strong>
            <p>
              {exportTarget === 'video'
                ? copy.videoNotesDescription
                : exportTarget === 'word'
                  ? wordModeDescription
                  : formatDescription}
            </p>
          </div>

          <div>
            <span className="field-label">{copy.outputRulesTitle}</span>
            <strong>{destinationDirectory}</strong>
            <p>{copy.outputRulesDescription}</p>
          </div>

          <div>
            <span className="field-label">{copy.videoNotesTitle}</span>
            <strong>{copy.videoStyleDescription}</strong>
            <p>{copy.videoNotesDescription}</p>
          </div>
        </div>
      </details>
    </SectionCard>
  )
}
