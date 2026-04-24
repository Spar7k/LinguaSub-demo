import type { ExportResult, ExportFormat, WordExportMode } from '../types/export'
import { useI18n } from '../i18n/useI18n'
import type { ImportResult } from '../types/import'
import type { OutputMode, ProjectState } from '../types/models'
import type {
  VideoBurnExportMode,
  VideoBurnExportResult,
} from '../types/videoExport'
import { safeTrim } from '../utils/config'
import { SectionCard } from './SectionCard'

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
  onOpenExportFolder: () => void
  onOpenVideoBurnExportFolder: () => void
  onExportFormatChange: (format: ExportFormat) => void
  onOutputModeChange: (mode: OutputMode) => void
  onWordExportModeChange: (mode: WordExportMode) => void
  onFileNameChange: (value: string) => void
  onVideoBurnModeChange: (mode: VideoBurnExportMode) => void
  onExportBurnedVideo: () => void
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
  onOpenExportFolder,
  onOpenVideoBurnExportFolder,
  onExportFormatChange,
  onOutputModeChange,
  onWordExportModeChange,
  onFileNameChange,
  onVideoBurnModeChange,
  onExportBurnedVideo,
}: ExportWorkspaceProps) {
  const { m, language } = useI18n()
  const exportCopy =
    language === 'zh'
      ? {
          openFolder: '打开文件夹',
          conflictResolved: '检测到同名文件，已自动追加序号保存。',
          sanitized: '文件名中的非法字符已自动清洗。',
        }
      : {
          openFolder: 'Open folder',
          conflictResolved:
            'LinguaSub found an existing file with the same name and saved this export with an added number.',
          sanitized:
            'Unsupported characters were removed from the requested file name automatically.',
        }
  const videoExportCopy =
    language === 'zh'
      ? {
          title: '导出带字幕视频',
          description:
            '把当前完整字幕烧录到原视频上，另存为一个新的 MP4 文件。',
          modeLabel: '视频字幕模式',
          modeBilingual: '双语字幕',
          modeTranslated: '仅译文字幕',
          modeHint: '第一版使用固定样式：底部居中、白字黑边。',
          start: '选择保存位置并导出 MP4',
          exporting: '正在导出带字幕视频...',
          noVideo:
            '当前项目没有原视频路径。请先从“视频字幕”入口生成字幕，再导出带字幕视频。',
          noSegments: '当前还没有字幕内容，先完成识别/翻译后再导出视频。',
          successTitle: '带字幕视频导出完成',
          successDescription: (fileName: string) =>
            `已生成 ${fileName}，可以打开所在目录查看。`,
          openFolder: '打开所在目录',
        }
      : {
          title: 'Export subtitled video',
          description:
            'Burn the full current subtitles into the original video and save a new MP4 file.',
          modeLabel: 'Video subtitle mode',
          modeBilingual: 'Bilingual subtitles',
          modeTranslated: 'Translated subtitles only',
          modeHint: 'MVP styling is fixed: bottom centered, white text with black outline.',
          start: 'Choose save location and export MP4',
          exporting: 'Exporting subtitled video...',
          noVideo:
            'This project does not have an original video path. Start from Video subtitle first.',
          noSegments: 'There are no subtitles yet. Finish recognition/translation first.',
          successTitle: 'Subtitled video exported',
          successDescription: (fileName: string) =>
            `${fileName} was created. You can open its folder now.`,
          openFolder: 'Open folder',
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
  const canExportBurnedVideo =
    Boolean(currentVideoPath) &&
    projectState.segments.length > 0 &&
    !isExporting &&
    !isVideoBurnExporting
  const effectiveFileName =
    safeTrim(exportFileName) ||
    getDefaultFileName(currentFilePath, exportFormat, outputMode, wordExportMode)
  const destinationDirectory =
    getDirectoryLabel(currentFilePath) || m.exportPage.currentProjectFolder
  const workflowLabel = importResult
    ? importResult.workflow
        .map((step) => m.common.workflowSteps[step as keyof typeof m.common.workflowSteps] ?? step)
        .join(' -> ')
    : ''
  const exportFormatLabel =
    exportFormat === 'word'
      ? m.common.exportFormats.word
      : m.common.exportFormats.srt
  const formatValue =
    exportFormat === 'word'
      ? m.exportPage.fileFormatValues.word
      : m.exportPage.fileFormatValues.srt
  const formatDescription =
    exportFormat === 'word'
      ? m.exportPage.fileFormatDescriptions.word
      : m.exportPage.fileFormatDescriptions.srt
  const wordModeDescription =
    wordExportMode === 'transcript'
      ? m.exportPage.wordModeDescriptions.transcript
      : m.exportPage.wordModeDescriptions.bilingualTable

  return (
    <>
      <SectionCard
        eyebrow={m.exportPage.sections.export.eyebrow}
        title={m.exportPage.sections.export.title}
        description={m.exportPage.sections.export.description}
        className="span-7"
      >
        <div className="settings-grid">
          <label className="field-block">
            <span className="field-label">{m.exportPage.formatLabel}</span>
            <select
              className="select-input"
              value={exportFormat}
              onChange={(event) => onExportFormatChange(event.target.value as ExportFormat)}
            >
              <option value="srt">{m.common.exportFormats.srt}</option>
              <option value="word">{m.common.exportFormats.word}</option>
            </select>
          </label>

          {exportFormat === 'srt' ? (
            <label className="field-block">
              <span className="field-label">{m.common.summary.outputMode}</span>
              <select
                className="select-input"
                value={outputMode}
                onChange={(event) => onOutputModeChange(event.target.value as OutputMode)}
              >
                <option value="bilingual">{m.common.outputModes.bilingual}</option>
                <option value="single">{m.common.outputModes.single}</option>
              </select>
            </label>
          ) : (
            <label className="field-block">
              <span className="field-label">{m.exportPage.wordModeLabel}</span>
              <select
                className="select-input"
                value={wordExportMode}
                onChange={(event) =>
                  onWordExportModeChange(event.target.value as WordExportMode)
                }
              >
                <option value="bilingualTable">
                  {m.common.wordExportModes.bilingualTable}
                </option>
                <option value="transcript">{m.common.wordExportModes.transcript}</option>
              </select>
            </label>
          )}

          <label className="field-block">
            <span className="field-label">{m.common.summary.resolvedFileName}</span>
            <input
              className="text-input"
              type="text"
              value={exportFileName}
              onChange={(event) => onFileNameChange(event.target.value)}
              placeholder={getDefaultFileName(
                currentFilePath,
                exportFormat,
                outputMode,
                wordExportMode,
              )}
              spellCheck={false}
            />
          </label>

          <div className="info-tile">
            <span className="field-label">{m.common.summary.destinationFolder}</span>
            <strong>{destinationDirectory}</strong>
            <p>{m.exportPage.destinationDescription}</p>
          </div>

          <div className="info-tile">
            <span className="field-label">{m.common.summary.resolvedFileName}</span>
            <strong>{effectiveFileName}</strong>
            <p>{m.exportPage.resolvedFileNameDescription}</p>
          </div>

          <div className="info-tile">
            <span className="field-label">{m.common.summary.exportFormat}</span>
            <strong>{formatValue}</strong>
            <p>{formatDescription}</p>
          </div>

          <div className="info-tile">
            <span className="field-label">
              {exportFormat === 'word'
                ? m.exportPage.wordModeLabel
                : m.common.summary.outputMode}
            </span>
            <strong>
              {exportFormat === 'word'
                ? m.common.wordExportModes[wordExportMode]
                : outputMode === 'bilingual'
                  ? m.common.outputModes.bilingual
                  : m.common.outputModes.single}
            </strong>
            <p>
              {exportFormat === 'word'
                ? wordModeDescription
                : outputMode === 'bilingual'
                  ? m.exportPage.bilingualDescription
                  : m.exportPage.singleDescription}
            </p>
          </div>

          <div className="info-tile">
            <span className="field-label">{m.common.summary.exportStatus}</span>
            <strong>
              {isExporting
                ? m.common.misc.writingFile
                : exportResult
                  ? m.common.misc.readyToExportAgain
                  : m.common.misc.notExportedYet}
            </strong>
            <p>
              {isExporting
                ? m.exportPage.writingDescription
                : m.exportPage.readyDescription(exportFormatLabel)}
            </p>
          </div>
        </div>

        {projectState.segments.length === 0 ? (
          <div className="error-banner" role="alert">
            <strong>{m.common.misc.noSubtitleContent}</strong>
            <p>{m.exportPage.noSubtitleDescription}</p>
          </div>
        ) : null}

        {exportFormat === 'srt' && outputMode === 'bilingual' && missingTranslationCount > 0 ? (
          <div className="warning-banner" role="alert">
            <strong>{m.common.misc.missingTranslatedLines}</strong>
            <p>{m.exportPage.missingLinesDescription(missingTranslationCount)}</p>
          </div>
        ) : null}

        {exportFormat === 'word' && missingTranslationCount > 0 ? (
          <div className="warning-banner" role="alert">
            <strong>{m.common.misc.missingTranslatedLines}</strong>
            <p>{m.exportPage.wordMissingTranslationsDescription(missingTranslationCount)}</p>
          </div>
        ) : null}

        {invalidTimelineCount > 0 ? (
          <div
            className={exportFormat === 'word' ? 'warning-banner' : 'error-banner'}
            role="alert"
          >
            <strong>{m.common.misc.timelineNeedsAttention}</strong>
            <p>
              {exportFormat === 'word'
                ? m.exportPage.wordInvalidTimelineDescription(invalidTimelineCount)
                : m.exportPage.invalidTimelineDescription(invalidTimelineCount)}
            </p>
          </div>
        ) : null}

        {processError ? (
          <div className="error-banner" role="alert">
            <strong>{m.common.misc.exportFailed}</strong>
            <p>{processError}</p>
          </div>
        ) : null}

        {exportResult ? (
          <div className="success-banner" role="status">
            <strong>{m.common.misc.lastExportCompleted}</strong>
            <p>{m.exportPage.lastExportDescription(exportResult.fileName)}</p>
            <code className="path-preview">{exportResult.path}</code>
            {exportResult.conflictResolved || exportResult.sanitizedFileName ? (
              <p>
                {exportResult.conflictResolved
                  ? exportCopy.conflictResolved
                  : null}
                {exportResult.conflictResolved && exportResult.sanitizedFileName
                  ? ' '
                  : null}
                {exportResult.sanitizedFileName
                  ? exportCopy.sanitized
                  : null}
              </p>
            ) : null}
            <div className="inline-actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={onOpenExportFolder}
              >
                {exportCopy.openFolder}
              </button>
            </div>
          </div>
        ) : null}

        <div className="info-panel">
          <strong>{videoExportCopy.title}</strong>
          <p>{videoExportCopy.description}</p>

          <div className="settings-grid">
            <label className="field-block">
              <span className="field-label">{videoExportCopy.modeLabel}</span>
              <select
                className="select-input"
                value={videoBurnMode}
                onChange={(event) =>
                  onVideoBurnModeChange(event.target.value as VideoBurnExportMode)
                }
                disabled={isVideoBurnExporting || isExporting}
              >
                <option value="bilingual">{videoExportCopy.modeBilingual}</option>
                <option value="translated">{videoExportCopy.modeTranslated}</option>
              </select>
            </label>

            <div className="info-tile">
              <span className="field-label">{m.common.summary.sourceFile}</span>
              <strong>{currentVideoPath ? currentVideoName : '未找到原视频'}</strong>
              <p>
                {currentVideoPath
                  ? '将使用当前项目的原视频路径，不会使用预览过滤后的字幕。'
                  : videoExportCopy.noVideo}
              </p>
            </div>
          </div>

          <p>{videoExportCopy.modeHint}</p>
          {projectState.segments.length === 0 ? (
            <p>{videoExportCopy.noSegments}</p>
          ) : null}

          <div className="inline-actions">
            <button
              type="button"
              className="button button--secondary"
              onClick={onExportBurnedVideo}
              disabled={!canExportBurnedVideo}
            >
              {isVideoBurnExporting ? videoExportCopy.exporting : videoExportCopy.start}
            </button>
          </div>
        </div>

        {videoBurnExportResult ? (
          <div className="success-banner" role="status">
            <strong>{videoExportCopy.successTitle}</strong>
            <p>{videoExportCopy.successDescription(videoBurnExportResult.fileName)}</p>
            <code className="path-preview">{videoBurnExportResult.outputPath}</code>
            <div className="inline-actions">
              <button
                type="button"
                className="button button--secondary"
                onClick={onOpenVideoBurnExportFolder}
              >
                {videoExportCopy.openFolder}
              </button>
            </div>
          </div>
        ) : null}

        <div className="info-panel">
          <strong>{m.exportPage.extensionTitle}</strong>
          <p>
            {exportFormat === 'word'
              ? wordExportMode === 'transcript'
                ? m.exportPage.extensionDescriptions.wordTranscript
                : m.exportPage.extensionDescriptions.wordBilingualTable
              : m.exportPage.extensionDescriptions.srt}
          </p>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow={m.exportPage.sections.summary.eyebrow}
        title={m.exportPage.sections.summary.title}
        description={m.exportPage.sections.summary.description}
        className="span-5"
      >
        {importResult ? (
          <div className="summary-grid">
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.sourceFile}</span>
              <span className="summary-item__value">{importResult.currentFile.name}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.route}</span>
              <span className="summary-item__value">{workflowLabel}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.subtitleRows}</span>
              <span className="summary-item__value">{projectState.segments.length}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.translatedRows}</span>
              <span className="summary-item__value">
                {translatedCount} / {projectState.segments.length}
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.exportFormat}</span>
              <span className="summary-item__value">{formatValue}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.livePreviewEdits}</span>
              <span className="summary-item__value">
                {hasUnsavedChanges
                  ? m.common.misc.includedInExport
                  : m.common.misc.alreadySaved}
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.projectStatus}</span>
              <span className="summary-item__value">
                {m.common.statuses[projectState.status]}
              </span>
            </div>
          </div>
        ) : (
          <div className="empty-state">
            <h3>{m.common.misc.noProjectLoaded}</h3>
            <p>{m.exportPage.noProjectDescription}</p>
          </div>
        )}
      </SectionCard>
    </>
  )
}
