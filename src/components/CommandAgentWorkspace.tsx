import { Fragment, useState } from 'react'
import type { ReactNode } from 'react'

import { useI18n } from '../i18n/useI18n'
import { runCommandAgent } from '../services/commandAgentService'
import type {
  CommandAgentContextSummary,
  CommandAgentSessionItem,
  CommandAgentState,
} from '../types/commandAgent'
import type { AppConfig, OutputMode, SubtitleSegment } from '../types/models'
import { safeTrim } from '../utils/config'
import { SectionCard } from './SectionCard'

type CommandAgentWorkspaceProps = {
  segments: SubtitleSegment[]
  config: AppConfig | null
  videoName?: string | null
  videoPath?: string | null
  sourceFilePath?: string | null
  sourceLanguage?: string | null
  targetLanguage?: string | null
  bilingualMode?: OutputMode | null
  segmentSignature?: string
  commandAgentState: CommandAgentState
  onSaveCommandAgentResult: (item: CommandAgentSessionItem) => void
  onSelectCommandAgentResult: (id: string) => void
}

function formatLanguageDirection(
  sourceLanguage: string | null | undefined,
  targetLanguage: string | null | undefined,
  fallback: string,
): string {
  const source = safeTrim(sourceLanguage ?? '')
  const target = safeTrim(targetLanguage ?? '')

  if (source && target) {
    return `${source} -> ${target}`
  }

  if (source) {
    return source
  }

  if (target) {
    return target
  }

  return fallback
}

type AiWorkbenchCopy = ReturnType<typeof useI18n>['m']['aiWorkbench']

function getRunErrorHint(message: string, copy: AiWorkbenchCopy): string {
  const normalizedMessage = message.toLowerCase()

  if (
    normalizedMessage.includes('could not reach') ||
    normalizedMessage.includes('failed to fetch') ||
    normalizedMessage.includes('networkerror')
  ) {
    return copy.errorHints.backendUnavailable
  }

  if (
    normalizedMessage.includes('route not found') ||
    normalizedMessage.includes('/agent/command') ||
    normalizedMessage.includes('404')
  ) {
    return copy.errorHints.routeMissing
  }

  if (
    normalizedMessage.includes('api key') ||
    normalizedMessage.includes('base url') ||
    normalizedMessage.includes('baseurl') ||
    normalizedMessage.includes('model') ||
    normalizedMessage.includes('provider') ||
    normalizedMessage.includes('configuration') ||
    normalizedMessage.includes('config')
  ) {
    return copy.errorHints.apiConfig
  }

  if (
    normalizedMessage.includes('json') ||
    normalizedMessage.includes('incomplete') ||
    normalizedMessage.includes('invalid') ||
    normalizedMessage.includes('parse')
  ) {
    return copy.errorHints.invalidJson
  }

  return copy.errorHints.default
}

type AgentContentBlock =
  | {
      type: 'heading'
      text: string
    }
  | {
      type: 'paragraph'
      lines: string[]
    }

function renderInlineContent(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const boldPattern = /\*\*([^*]+?)\*\*/g
  let cursor = 0
  let match = boldPattern.exec(text)

  while (match) {
    const matchIndex = match.index

    if (matchIndex > cursor) {
      nodes.push(text.slice(cursor, matchIndex))
    }

    nodes.push(
      <strong
        className="ai-workbench-content-bold"
        key={`${keyPrefix}-bold-${matchIndex}`}
      >
        {match[1]}
      </strong>,
    )

    cursor = matchIndex + match[0].length
    match = boldPattern.exec(text)
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor))
  }

  return nodes.length > 0 ? nodes : [text]
}

function renderAgentContent(text: string) {
  const blocks: AgentContentBlock[] = []
  let paragraphLines: string[] = []

  function flushParagraph() {
    if (paragraphLines.length === 0) {
      return
    }

    blocks.push({
      type: 'paragraph',
      lines: paragraphLines,
    })
    paragraphLines = []
  }

  text
    .replace(/\r\n/g, '\n')
    .split('\n')
    .forEach((line) => {
      const trimmedLine = line.trim()

      if (!trimmedLine) {
        flushParagraph()
        return
      }

      if (trimmedLine.startsWith('##')) {
        flushParagraph()
        const headingText = trimmedLine.replace(/^##+\s*/, '').trim()

        if (headingText) {
          blocks.push({
            type: 'heading',
            text: headingText,
          })
        }
        return
      }

      paragraphLines.push(trimmedLine)
    })

  flushParagraph()

  if (blocks.length === 0) {
    return null
  }

  return (
    <div className="ai-workbench-content">
      {blocks.map((block, blockIndex) => (
        <div className="ai-workbench-content-section" key={blockIndex}>
          {block.type === 'heading' ? (
            <h4 className="ai-workbench-content-heading">
              {renderInlineContent(block.text, `heading-${blockIndex}`)}
            </h4>
          ) : (
            <p className="ai-workbench-content-paragraph">
              {block.lines.map((line, lineIndex) => (
                <Fragment key={`${blockIndex}-${lineIndex}`}>
                  {lineIndex > 0 ? <br /> : null}
                  {renderInlineContent(
                    line,
                    `paragraph-${blockIndex}-${lineIndex}`,
                  )}
                </Fragment>
              ))}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

export function CommandAgentWorkspace({
  segments,
  config,
  videoName,
  videoPath,
  sourceFilePath,
  sourceLanguage,
  targetLanguage,
  bilingualMode,
  segmentSignature,
  commandAgentState,
  onSaveCommandAgentResult,
  onSelectCommandAgentResult,
}: CommandAgentWorkspaceProps) {
  const { m } = useI18n()
  const copy = m.aiWorkbench
  const subtitleCount = segments.length
  const hasSubtitles = subtitleCount > 0
  const translatedCount = segments.filter((segment) =>
    safeTrim(segment.translatedText),
  ).length
  const [instruction, setInstruction] = useState('')
  const [alertMessage, setAlertMessage] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const translatedRate =
    subtitleCount > 0 ? Math.round((translatedCount / subtitleCount) * 100) : 0
  const languageDirection = formatLanguageDirection(
    sourceLanguage,
    targetLanguage,
    copy.unknownLanguageDirection,
  )
  const historyItems = commandAgentState.items.slice(0, 10)
  const activeItem =
    commandAgentState.items.find(
      (item) => item.id === commandAgentState.activeItemId,
    ) ?? commandAgentState.items[0]
  const trimmedInstruction = safeTrim(instruction)
  const canRetry = Boolean(runError && trimmedInstruction && !isRunning)
  const runErrorHint = runError ? getRunErrorHint(runError, copy) : ''

  function buildContextSummary(): CommandAgentContextSummary {
    return {
      videoName: safeTrim(videoName ?? '') || undefined,
      videoPath: safeTrim(videoPath ?? '') || undefined,
      sourceFilePath: safeTrim(sourceFilePath ?? '') || undefined,
      subtitleCount,
      translatedCount,
      translationCoverage: translatedRate,
      sourceLanguage: safeTrim(sourceLanguage ?? '') || undefined,
      targetLanguage: safeTrim(targetLanguage ?? '') || undefined,
      bilingualMode: bilingualMode ?? undefined,
    }
  }

  async function handleRunCommand() {
    if (isRunning) {
      return
    }

    if (!hasSubtitles) {
      setAlertMessage(copy.noSubtitleRunError)
      setRunError(null)
      return
    }

    if (!trimmedInstruction) {
      setAlertMessage(copy.emptyInstruction)
      setRunError(null)
      return
    }

    if (!config) {
      setAlertMessage(copy.apiConfigMissing)
      setRunError(null)
      return
    }

    setAlertMessage(null)
    setRunError(null)
    setIsRunning(true)

    try {
      const result = await runCommandAgent({
        instruction: trimmedInstruction,
        segments,
        config,
        context: {
          videoName: safeTrim(videoName ?? '') || undefined,
          videoPath: safeTrim(videoPath ?? '') || undefined,
          sourceLanguage: safeTrim(sourceLanguage ?? '') || undefined,
          targetLanguage: safeTrim(targetLanguage ?? '') || undefined,
          bilingualMode: bilingualMode ?? undefined,
        },
        timeoutSeconds: 60,
      })

      onSaveCommandAgentResult({
        id: `command-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        instruction: trimmedInstruction,
        createdAt: new Date().toISOString(),
        contextSummary: buildContextSummary(),
        segmentSignature,
        result,
      })
    } catch (error) {
      setRunError(error instanceof Error ? error.message : copy.runFailed)
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <>
      <SectionCard
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.subtitle}
        className="span-12 ai-workbench-hero"
      >
        <div className="ai-workbench-shell">
          <div className="ai-workbench-command-card">
            <label className="field-block" htmlFor="ai-workbench-command-input">
              <span className="field-label">{copy.instructionTitle}</span>
              <textarea
                id="ai-workbench-command-input"
                className="ai-workbench-input"
                value={instruction}
                onChange={(event) => {
                  setInstruction(event.target.value)
                  setAlertMessage(null)
                  setRunError(null)
                }}
                placeholder={copy.instructionPlaceholder}
                rows={4}
              />
            </label>
            {isRunning ? (
              <p className="ai-workbench-loading-note" role="status">
                {copy.generatingDescription}
              </p>
            ) : null}
            <div className="ai-workbench-command-card__footer">
              <p>{copy.instructionDescription}</p>
              <button
                type="button"
                className="button button--primary"
                disabled={isRunning}
                onClick={() => {
                  void handleRunCommand()
                }}
              >
                {isRunning ? copy.generating : copy.runButton}
              </button>
            </div>
          </div>

          <div className="ai-workbench-examples">
            <span className="field-label">{copy.examplesTitle}</span>
            <div className="ai-workbench-example-grid">
              {copy.examplePrompts.map((example) => (
                <button
                  key={example.title}
                  type="button"
                  className="ai-workbench-example-card"
                  onClick={() => {
                    setInstruction(example.prompt)
                    setAlertMessage(null)
                    setRunError(null)
                  }}
                >
                  <strong>{example.title}</strong>
                  <span>{example.prompt}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        eyebrow={copy.contextEyebrow}
        title={copy.contextTitle}
        description={copy.contextDescription}
        className="span-7"
      >
        <div className="ai-workbench-context-grid">
          <div className="summary-item">
            <span className="summary-item__label">{copy.videoName}</span>
            <span className="summary-item__value">
              {safeTrim(videoName ?? '') || copy.noVideo}
            </span>
            {videoPath ? (
              <span className="ai-workbench-path">{videoPath}</span>
            ) : null}
          </div>
          <div className="summary-item">
            <span className="summary-item__label">{copy.subtitleCount}</span>
            <span className="summary-item__value">{subtitleCount}</span>
          </div>
          <div className="summary-item">
            <span className="summary-item__label">{copy.translatedCount}</span>
            <span className="summary-item__value">
              {translatedCount} / {subtitleCount}
            </span>
            <span className="ai-workbench-path">
              {copy.translatedRate(translatedRate)}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-item__label">{copy.languageDirection}</span>
            <span className="summary-item__value">{languageDirection}</span>
          </div>
          <div className="summary-item">
            <span className="summary-item__label">{copy.bilingualMode}</span>
            <span className="summary-item__value">
              {bilingualMode ? m.common.outputModes[bilingualMode] : copy.notConfigured}
            </span>
          </div>
        </div>

        {subtitleCount === 0 ? (
          <div className="empty-state ai-workbench-empty" role="status">
            <h3>{copy.emptyTitle}</h3>
            <p>{copy.emptyDescription}</p>
          </div>
        ) : null}
      </SectionCard>

      <SectionCard
        eyebrow={copy.comingSoonEyebrow}
        title={copy.comingSoonTitle}
        description={copy.comingSoonDescription}
        className="span-5"
      >
        <div className="ai-workbench-capability-list">
          {copy.comingSoonItems.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        eyebrow={copy.resultEyebrow}
        title={copy.resultTitle}
        description={copy.resultDescription}
        className="span-12"
      >
        <div className="ai-workbench-result-card">
          {alertMessage ? (
            <div className="ai-workbench-alert" role="alert">
              {alertMessage}
            </div>
          ) : null}
          {runError ? (
            <div className="ai-workbench-error-card" role="alert">
              <div>
                <strong className="ai-workbench-error-title">
                  {copy.errorTitle}
                </strong>
                <p className="ai-workbench-error-message">
                  {runError || copy.runFailed}
                </p>
              </div>
              <div className="ai-workbench-error-suggestion">
                <span>{copy.errorSuggestionTitle}</span>
                <p>{runErrorHint}</p>
              </div>
              {canRetry ? (
                <div className="ai-workbench-error-actions">
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={() => {
                      void handleRunCommand()
                    }}
                  >
                    {copy.retry}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="ai-workbench-result-layout">
            <div className="ai-workbench-result-main">
              {activeItem ? (
                <div className="ai-workbench-result-grid">
                  <section>
                    <span className="field-label">{copy.activeResult}</span>
                    <strong>{activeItem.result.title}</strong>
                    <span className="ai-workbench-result-meta">
                      {copy.createdAt(
                        new Date(activeItem.createdAt).toLocaleString(),
                      )}
                    </span>
                  </section>
                  <section>
                    <span className="field-label">{copy.understoodTask}</span>
                    <p>{activeItem.instruction}</p>
                  </section>
                  <section>
                    <span className="field-label">{copy.summaryTitle}</span>
                    <p>{activeItem.result.summary}</p>
                  </section>
                  <section>
                    <span className="field-label">{copy.outputTitle}</span>
                    {renderAgentContent(activeItem.result.content)}
                  </section>
                  <section>
                    <span className="field-label">{copy.suggestedActionsTitle}</span>
                    <div className="ai-workbench-suggestion-list">
                      {activeItem.result.suggestedActions.map((action) => (
                        <span className="ai-workbench-suggestion-chip" key={action}>
                          {action}
                        </span>
                      ))}
                    </div>
                  </section>
                </div>
              ) : (
                <p className="ai-workbench-result-placeholder">
                  {copy.resultPlaceholder}
                </p>
              )}
            </div>

            <aside className="ai-workbench-history-card">
              <div className="ai-workbench-history-title">
                <span className="field-label">{copy.historyTitle}</span>
                <strong>{copy.recentResult}</strong>
              </div>
              {historyItems.length > 0 ? (
                <div className="ai-workbench-history-list">
                  {historyItems.map((item) => {
                    const isActive = item.id === activeItem?.id
                    return (
                      <button
                        key={item.id}
                        type="button"
                        className={
                          isActive
                            ? 'ai-workbench-history-item ai-workbench-history-item-active'
                            : 'ai-workbench-history-item'
                        }
                        onClick={() => onSelectCommandAgentResult(item.id)}
                      >
                        <span className="ai-workbench-history-item__title">
                          {item.result.title || copy.historyInstructionFallback}
                        </span>
                        <span className="ai-workbench-history-item__instruction">
                          {item.instruction || copy.historyInstructionFallback}
                        </span>
                        <span className="ai-workbench-history-meta">
                          {new Date(item.createdAt).toLocaleString()}
                        </span>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <p className="ai-workbench-result-placeholder">{copy.noHistory}</p>
              )}
            </aside>
          </div>
        </div>
      </SectionCard>
    </>
  )
}
