import { useMemo, useState } from 'react'

import { useI18n } from '../i18n/useI18n'
import {
  analyzeSubtitleQuality,
  summarizeSubtitleContent,
} from '../services/agentService'
import type {
  AgentIssueSeverity,
  AgentIssueType,
  ContentSummaryResult,
  SubtitleAgentRequest,
  SubtitleQualityResult,
} from '../types/agent'
import type { AppConfig, SubtitleSegment } from '../types/models'
import { hasUsableTranslationConfig, safeTrim } from '../utils/config'
import { SectionCard } from './SectionCard'

type SubtitleAgentPanelProps = {
  segments: SubtitleSegment[]
  config: AppConfig | null
  sourceLanguage?: string
  targetLanguage?: string
  bilingualMode?: string
}

function normalizeTimeValue(value: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0
}

function formatMilliseconds(value: number): string {
  const totalMilliseconds = normalizeTimeValue(value)
  const milliseconds = totalMilliseconds % 1000
  const totalSeconds = Math.floor(totalMilliseconds / 1000)
  const seconds = totalSeconds % 60
  const totalMinutes = Math.floor(totalSeconds / 60)
  const minutes = totalMinutes % 60
  const hours = Math.floor(totalMinutes / 60)

  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(
    seconds,
  ).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`
}

function normalizeScore(score: number): number {
  if (!Number.isFinite(score)) {
    return 0
  }

  return Math.max(0, Math.min(100, Math.round(score)))
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && safeTrim(error.message)
    ? error.message
    : fallback
}

export function SubtitleAgentPanel({
  segments,
  config,
  sourceLanguage,
  targetLanguage,
  bilingualMode,
}: SubtitleAgentPanelProps) {
  const { m } = useI18n()
  const agentMessages = m.previewPage.agent
  const [subtitleQualityAgentLoading, setSubtitleQualityAgentLoading] =
    useState(false)
  const [subtitleQualityAgentError, setSubtitleQualityAgentError] = useState<
    string | null
  >(null)
  const [subtitleQualityAgentResult, setSubtitleQualityAgentResult] =
    useState<SubtitleQualityResult | null>(null)
  const [contentSummaryAgentLoading, setContentSummaryAgentLoading] =
    useState(false)
  const [contentSummaryAgentError, setContentSummaryAgentError] = useState<
    string | null
  >(null)
  const [contentSummaryAgentResult, setContentSummaryAgentResult] =
    useState<ContentSummaryResult | null>(null)

  const hasSegments = segments.length > 0
  const fallbackSourceLanguage =
    sourceLanguage ?? segments.find((segment) => safeTrim(segment.sourceLanguage))?.sourceLanguage
  const fallbackTargetLanguage =
    targetLanguage ?? segments.find((segment) => safeTrim(segment.targetLanguage))?.targetLanguage
  const issueTypeLabels = agentMessages.issueTypes as Record<AgentIssueType, string>
  const severityLabels = agentMessages.severities as Record<
    AgentIssueSeverity,
    string
  >

  const agentRequestSegments = useMemo(
    () =>
      segments.map((segment) => ({
        id: segment.id,
        start: normalizeTimeValue(segment.start),
        end: normalizeTimeValue(segment.end),
        sourceText: segment.sourceText,
        translatedText: segment.translatedText ?? '',
        sourceLanguage: segment.sourceLanguage || fallbackSourceLanguage || 'auto',
        targetLanguage: segment.targetLanguage || fallbackTargetLanguage || 'zh-CN',
      })),
    [fallbackSourceLanguage, fallbackTargetLanguage, segments],
  )

  function buildAgentRequest(resolvedConfig: AppConfig): SubtitleAgentRequest {
    return {
      segments: agentRequestSegments,
      config: resolvedConfig,
      sourceLanguage: fallbackSourceLanguage,
      targetLanguage: fallbackTargetLanguage,
      bilingualMode,
      timeoutSeconds: 60,
    }
  }

  async function handleAnalyzeQuality() {
    if (!hasSegments) {
      return
    }

    if (!hasUsableTranslationConfig(config)) {
      setSubtitleQualityAgentError(agentMessages.configError)
      return
    }

    setSubtitleQualityAgentLoading(true)
    setSubtitleQualityAgentError(null)
    setSubtitleQualityAgentResult(null)

    try {
      const result = await analyzeSubtitleQuality(buildAgentRequest(config))
      setSubtitleQualityAgentResult(result)
    } catch (error) {
      setSubtitleQualityAgentError(
        getErrorMessage(error, agentMessages.qualityError),
      )
    } finally {
      setSubtitleQualityAgentLoading(false)
    }
  }

  async function handleGenerateSummary() {
    if (!hasSegments) {
      return
    }

    if (!hasUsableTranslationConfig(config)) {
      setContentSummaryAgentError(agentMessages.configError)
      return
    }

    setContentSummaryAgentLoading(true)
    setContentSummaryAgentError(null)
    setContentSummaryAgentResult(null)

    try {
      const result = await summarizeSubtitleContent(buildAgentRequest(config))
      setContentSummaryAgentResult(result)
    } catch (error) {
      setContentSummaryAgentError(
        getErrorMessage(error, agentMessages.summaryError),
      )
    } finally {
      setContentSummaryAgentLoading(false)
    }
  }

  return (
    <SectionCard
      eyebrow={agentMessages.eyebrow}
      title={agentMessages.title}
      description={agentMessages.description}
      className="span-12"
    >
      <div className="agent-panel">
        {!hasSegments ? (
          <div className="empty-state">
            <h3>{agentMessages.emptyTitle}</h3>
            <p>{agentMessages.emptyDescription}</p>
          </div>
        ) : null}

        <div className="agent-actions">
          <button
            className="button button--primary"
            type="button"
            disabled={!hasSegments || subtitleQualityAgentLoading}
            onClick={() => {
              void handleAnalyzeQuality()
            }}
          >
            {subtitleQualityAgentLoading
              ? agentMessages.actions.analyzingQuality
              : agentMessages.actions.analyzeQuality}
          </button>
          <button
            className="button button--secondary"
            type="button"
            disabled={!hasSegments || contentSummaryAgentLoading}
            onClick={() => {
              void handleGenerateSummary()
            }}
          >
            {contentSummaryAgentLoading
              ? agentMessages.actions.generatingSummary
              : agentMessages.actions.generateSummary}
          </button>
        </div>

        <div className="agent-result-grid">
          <section className="agent-result">
            <div className="agent-result__header">
              <div>
                <h3>{agentMessages.qualityTitle}</h3>
                <p>{agentMessages.qualityDescription}</p>
              </div>
              {subtitleQualityAgentResult ? (
                <span className="agent-score">
                  {normalizeScore(subtitleQualityAgentResult.score)}
                  <small>{agentMessages.scoreLabel}</small>
                </span>
              ) : null}
            </div>

            {subtitleQualityAgentError ? (
              <div className="error-banner">
                <p>{subtitleQualityAgentError}</p>
              </div>
            ) : null}

            {subtitleQualityAgentResult ? (
              <div className="agent-summary-section">
                <p className="agent-note">{subtitleQualityAgentResult.summary}</p>
                <h4>{agentMessages.issuesTitle}</h4>
                {subtitleQualityAgentResult.issues.length > 0 ? (
                  <div className="agent-issue-list">
                    {subtitleQualityAgentResult.issues.map((issue, index) => (
                      <article
                        className="agent-issue"
                        key={`${issue.segmentId}-${issue.type}-${index}`}
                      >
                        <div className="agent-issue__meta">
                          <span
                            className={`agent-severity agent-severity--${issue.severity}`}
                          >
                            {severityLabels[issue.severity]}
                          </span>
                          <span>{issueTypeLabels[issue.type]}</span>
                          <span>{issue.segmentId}</span>
                        </div>
                        <p>{issue.message}</p>
                        {issue.suggestion ? (
                          <p className="agent-suggestion">{issue.suggestion}</p>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="agent-note">{agentMessages.noIssues}</p>
                )}
              </div>
            ) : null}
          </section>

          <section className="agent-result">
            <div className="agent-result__header">
              <div>
                <h3>{agentMessages.summaryTitle}</h3>
                <p>{agentMessages.summaryDescription}</p>
              </div>
            </div>

            {contentSummaryAgentError ? (
              <div className="error-banner">
                <p>{contentSummaryAgentError}</p>
              </div>
            ) : null}

            {contentSummaryAgentResult ? (
              <div className="agent-summary-section">
                <h4>{agentMessages.oneSentenceTitle}</h4>
                <p className="agent-note">
                  {contentSummaryAgentResult.oneSentenceSummary}
                </p>

                <h4>{agentMessages.chaptersTitle}</h4>
                {contentSummaryAgentResult.chapters.length > 0 ? (
                  <div className="agent-chapter-list">
                    {contentSummaryAgentResult.chapters.map((chapter, index) => (
                      <article
                        className="agent-chapter"
                        key={`${chapter.start}-${chapter.end}-${index}`}
                      >
                        <span className="agent-time-range">
                          {formatMilliseconds(chapter.start)} -{' '}
                          {formatMilliseconds(chapter.end)}
                        </span>
                        <strong>{chapter.title}</strong>
                        <p>{chapter.summary}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="agent-note">{agentMessages.noChapters}</p>
                )}

                <h4>{agentMessages.keywordsTitle}</h4>
                {contentSummaryAgentResult.keywords.length > 0 ? (
                  <div className="agent-keyword-list">
                    {contentSummaryAgentResult.keywords.map((keyword, index) => (
                      <div className="agent-keyword" key={`${keyword.term}-${index}`}>
                        <strong>{keyword.term}</strong>
                        {keyword.translation ? <span>{keyword.translation}</span> : null}
                        {keyword.explanation ? <p>{keyword.explanation}</p> : null}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="agent-note">{agentMessages.noKeywords}</p>
                )}

                <h4>{agentMessages.studyNotesTitle}</h4>
                <p className="agent-note agent-note--prewrap">
                  {contentSummaryAgentResult.studyNotes}
                </p>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </SectionCard>
  )
}
