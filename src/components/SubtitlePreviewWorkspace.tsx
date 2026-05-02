import { useDeferredValue, useMemo, useState } from 'react'

import { useI18n } from '../i18n/useI18n'
import type { ContentSummaryResult, SubtitleQualityResult } from '../types/agent'
import type { ImportResult } from '../types/import'
import type { AppConfig, ProjectState, ProviderName, SubtitleSegment } from '../types/models'
import type { TaskLogEntry } from '../types/tasks'
import { safeTrim } from '../utils/config'
import { EditableSubtitleRow } from './EditableSubtitleRow'
import { SectionCard } from './SectionCard'
import { SubtitleAgentPanel } from './SubtitleAgentPanel'
import { SubtitleSearchToolbar } from './SubtitleSearchToolbar'
import { TaskLogPanel } from './TaskLogPanel'

type TranslationRunMeta = {
  provider: ProviderName
  model: string
} | null

type SubtitlePreviewWorkspaceProps = {
  projectState: ProjectState
  importResult: ImportResult | null
  config: AppConfig | null
  translationRun: TranslationRunMeta
  taskLogs: TaskLogEntry[]
  hasUnsavedChanges: boolean
  lastSavedAt: string | null
  currentSegmentSignature: string
  subtitleQualityAgentResult: SubtitleQualityResult | null
  contentSummaryAgentResult: ContentSummaryResult | null
  isSubtitleQualityAgentStale: boolean
  isContentSummaryAgentStale: boolean
  onUpdateSegment: (
    segmentId: string,
    patch: Pick<SubtitleSegment, 'sourceText' | 'translatedText'>,
  ) => void
  onSaveSegments: () => void
  onRetranslateSegment: (segment: SubtitleSegment) => Promise<void>
  onSubtitleQualityAgentResultChange: (
    result: SubtitleQualityResult,
    segmentSignature: string,
    segmentCount: number,
  ) => void
  onContentSummaryAgentResultChange: (
    result: ContentSummaryResult,
    segmentSignature: string,
    segmentCount: number,
  ) => void
}

export function SubtitlePreviewWorkspace({
  projectState,
  importResult,
  config,
  translationRun,
  taskLogs,
  hasUnsavedChanges,
  lastSavedAt,
  currentSegmentSignature,
  subtitleQualityAgentResult,
  contentSummaryAgentResult,
  isSubtitleQualityAgentStale,
  isContentSummaryAgentStale,
  onUpdateSegment,
  onSaveSegments,
  onRetranslateSegment,
  onSubtitleQualityAgentResultChange,
  onContentSummaryAgentResultChange,
}: SubtitlePreviewWorkspaceProps) {
  const { m } = useI18n()
  const [searchQuery, setSearchQuery] = useState('')
  const [retranslatingIds, setRetranslatingIds] = useState<string[]>([])
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})
  const deferredSearchQuery = useDeferredValue(safeTrim(searchQuery).toLowerCase())
  const translatedCount = projectState.segments.filter((segment) => safeTrim(segment.translatedText)).length
  const firstSegment = projectState.segments[0]
  const filteredSegments = useMemo(() => {
    if (!deferredSearchQuery) {
      return projectState.segments
    }

    return projectState.segments.filter((segment) => {
      const source = (typeof segment.sourceText === 'string' ? segment.sourceText : '').toLowerCase()
      const translated =
        (typeof segment.translatedText === 'string' ? segment.translatedText : '').toLowerCase()
      return source.includes(deferredSearchQuery) || translated.includes(deferredSearchQuery)
    })
  }, [deferredSearchQuery, projectState.segments])

  function clearRowError(segmentId: string) {
    setRowErrors((current) => {
      if (!(segmentId in current)) {
        return current
      }

      const next = { ...current }
      delete next[segmentId]
      return next
    })
  }

  async function handleRetranslate(segment: SubtitleSegment) {
    clearRowError(segment.id)
    setRetranslatingIds((current) => [...current, segment.id])

    try {
      await onRetranslateSegment(segment)
    } catch (error) {
      const message =
        error instanceof Error ? error.message : m.previewPage.retranslationFailed
      setRowErrors((current) => ({
        ...current,
        [segment.id]: message,
      }))
    } finally {
      setRetranslatingIds((current) => current.filter((item) => item !== segment.id))
    }
  }

  const logPanelTitle =
    (m.previewPage as { logPanelTitle?: string }).logPanelTitle ?? 'Task logs'
  const logPanelDescription =
    (m.previewPage as { logPanelDescription?: string }).logPanelDescription ??
    'Use this panel to review the full task timeline when a test run needs diagnosis.'

  return (
    <>
      <SectionCard
        eyebrow={m.previewPage.sections.preview.eyebrow}
        title={m.previewPage.sections.preview.title}
        description={m.previewPage.sections.preview.description}
        className="span-4"
      >
        {importResult ? (
          <div className="summary-grid">
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.file}</span>
              <span className="summary-item__value">{importResult.currentFile.name}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.status}</span>
              <span className="summary-item__value">{m.common.statuses[projectState.status]}</span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.translatedSegments}</span>
              <span className="summary-item__value">
                {translatedCount} / {projectState.segments.length}
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.outputMode}</span>
              <span className="summary-item__value">
                {config ? m.common.outputModes[config.outputMode] : m.common.outputModes.bilingual}
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-item__label">{m.common.summary.filteredRows}</span>
              <span className="summary-item__value">
                {filteredSegments.length} / {projectState.segments.length}
              </span>
            </div>
            {translationRun ? (
              <div className="summary-item">
                <span className="summary-item__label">{m.common.summary.lastRun}</span>
                <span className="summary-item__value">
                  {m.common.providers[translationRun.provider]} / {translationRun.model}
                </span>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="empty-state">
            <h3>{m.common.misc.nothingToPreview}</h3>
            <p>{m.previewPage.nothingToPreviewDescription}</p>
          </div>
        )}
      </SectionCard>

      <SectionCard
        eyebrow={m.previewPage.sections.segments.eyebrow}
        title={m.previewPage.sections.segments.title}
        description={m.previewPage.sections.segments.description}
        className="span-8"
      >
        {projectState.segments.length > 0 ? (
          <div className="subtitle-editor">
            <SubtitleSearchToolbar
              searchQuery={searchQuery}
              visibleCount={filteredSegments.length}
              totalCount={projectState.segments.length}
              hasUnsavedChanges={hasUnsavedChanges}
              lastSavedAt={lastSavedAt}
              onSearchChange={setSearchQuery}
              onSaveChanges={onSaveSegments}
            />

            {filteredSegments.length > 0 ? (
              <div className="editor-list">
                {filteredSegments.map((segment) => (
                  <EditableSubtitleRow
                    key={segment.id}
                    segment={segment}
                    isRetranslating={retranslatingIds.includes(segment.id)}
                    errorMessage={rowErrors[segment.id] ?? null}
                    onSourceChange={(segmentId, value) => {
                      clearRowError(segmentId)
                      onUpdateSegment(segmentId, {
                        sourceText: value,
                        translatedText: segment.translatedText,
                      })
                    }}
                    onTranslationChange={(segmentId, value) => {
                      clearRowError(segmentId)
                      onUpdateSegment(segmentId, {
                        sourceText: segment.sourceText,
                        translatedText: value,
                      })
                    }}
                    onRetranslate={handleRetranslate}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <h3>{m.common.misc.noMatchesFound}</h3>
                <p>{m.previewPage.noMatchesDescription}</p>
              </div>
            )}
          </div>
        ) : (
          <div className="empty-state">
            <h3>{m.common.misc.noSegmentsAvailable}</h3>
            <p>{m.previewPage.noSegmentsDescription}</p>
          </div>
        )}
      </SectionCard>

      <SubtitleAgentPanel
        segments={projectState.segments}
        config={config}
        sourceLanguage={firstSegment?.sourceLanguage}
        targetLanguage={firstSegment?.targetLanguage}
        bilingualMode={config?.outputMode}
        currentSegmentSignature={currentSegmentSignature}
        subtitleQualityResult={subtitleQualityAgentResult}
        contentSummaryResult={contentSummaryAgentResult}
        isSubtitleQualityStale={isSubtitleQualityAgentStale}
        isContentSummaryStale={isContentSummaryAgentStale}
        onSubtitleQualityResultChange={onSubtitleQualityAgentResultChange}
        onContentSummaryResultChange={onContentSummaryAgentResultChange}
      />

      <SectionCard
        eyebrow={m.previewPage.sections.preview.eyebrow}
        title={logPanelTitle}
        description={logPanelDescription}
        className="span-12"
      >
        <TaskLogPanel
          logs={taskLogs}
          title={logPanelTitle}
          description={logPanelDescription}
        />
      </SectionCard>
    </>
  )
}
