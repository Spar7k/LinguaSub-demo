import { useMemo, useState } from 'react'

import { useI18n } from '../i18n/useI18n'
import type { TaskLogEntry } from '../types/tasks'

type TaskLogPanelProps = {
  logs: TaskLogEntry[]
  title?: string
  description?: string
  emptyTitle?: string
  emptyDescription?: string
  highlightLatestError?: boolean
}

function formatLogTime(timestamp: string): string {
  if (!timestamp) {
    return '--'
  }

  const value = new Date(timestamp)
  if (Number.isNaN(value.getTime())) {
    return timestamp
  }

  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(value)
}

function getLogTone(level: TaskLogEntry['level']): string {
  if (level === 'error') {
    return 'error'
  }

  if (level === 'warning') {
    return 'warn'
  }

  return 'idle'
}

export function TaskLogPanel({
  logs,
  title,
  description,
  emptyTitle,
  emptyDescription,
  highlightLatestError = true,
}: TaskLogPanelProps) {
  const { language } = useI18n()
  const [isExpanded, setIsExpanded] = useState(false)
  const [copyMessage, setCopyMessage] = useState<string | null>(null)

  const copy = useMemo(
    () =>
      language === 'zh'
        ? {
            title: title ?? '任务日志',
            description:
              description ?? '默认收起。需要排查问题时，可以展开查看本次任务的处理过程。',
            toggleOpen: '查看日志',
            toggleClose: '收起日志',
            emptyTitle: emptyTitle ?? '暂时还没有日志',
            emptyDescription:
              emptyDescription ?? '开始处理后，这里会记录识别、翻译和导出的关键步骤。',
            copied: '日志已复制',
            copy: '复制日志',
            details: '技术细节',
            latestError: '最近错误',
            technicalEmpty: '暂无额外技术细节',
            level: {
              info: '信息',
              warning: '警告',
              error: '错误',
            },
          }
        : {
            title: title ?? 'Task logs',
            description:
              description ??
              'Logs stay collapsed by default so normal users are not distracted by technical details.',
            toggleOpen: 'View logs',
            toggleClose: 'Hide logs',
            emptyTitle: emptyTitle ?? 'No logs yet',
            emptyDescription:
              emptyDescription ??
              'LinguaSub will record recognition, translation, and export events here once the task starts.',
            copied: 'Logs copied',
            copy: 'Copy logs',
            details: 'Technical details',
            latestError: 'Latest error',
            technicalEmpty: 'No extra technical details',
            level: {
              info: 'Info',
              warning: 'Warning',
              error: 'Error',
            },
          },
    [description, emptyDescription, emptyTitle, language, title],
  )

  const latestErrorLog = highlightLatestError
    ? [...logs].reverse().find((entry) => entry.level === 'error') ?? null
    : null

  async function handleCopyLogs() {
    if (logs.length === 0 || !navigator.clipboard?.writeText) {
      return
    }

    const payload = logs
      .map((entry) => {
        const details = entry.details ? `\n${entry.details}` : ''
        return `[${formatLogTime(entry.timestamp)}] ${copy.level[entry.level]} ${entry.message}${details}`
      })
      .join('\n\n')

    await navigator.clipboard.writeText(payload)
    setCopyMessage(copy.copied)
    window.setTimeout(() => {
      setCopyMessage(null)
    }, 1800)
  }

  return (
    <div className="log-panel">
      <div className="log-panel__header">
        <div>
          <h3>{copy.title}</h3>
          <p>{copy.description}</p>
        </div>
        <div className="log-panel__actions">
          {logs.length > 0 ? (
            <>
              <button
                type="button"
                className="button button--secondary"
                onClick={handleCopyLogs}
              >
                {copy.copy}
              </button>
              <button
                type="button"
                className="button button--secondary"
                onClick={() => setIsExpanded((current) => !current)}
              >
                {isExpanded ? copy.toggleClose : copy.toggleOpen}
              </button>
            </>
          ) : null}
        </div>
      </div>

      {copyMessage ? <p className="helper-text">{copyMessage}</p> : null}

      {latestErrorLog ? (
        <div className="error-banner task-log-panel__highlight" role="alert">
          <strong>{copy.latestError}</strong>
          <p>{latestErrorLog.message}</p>
        </div>
      ) : null}

      {logs.length === 0 ? (
        <div className="empty-state">
          <h3>{copy.emptyTitle}</h3>
          <p>{copy.emptyDescription}</p>
        </div>
      ) : null}

      {logs.length > 0 && isExpanded ? (
        <div className="log-list">
          {logs.map((entry) => (
            <article key={entry.logId} className="log-entry">
              <div className="log-entry__head">
                <div>
                  <span className="log-entry__time">{formatLogTime(entry.timestamp)}</span>
                  <strong>{entry.message}</strong>
                </div>
                <span className={`status-pill status-pill--${getLogTone(entry.level)}`}>
                  {copy.level[entry.level]}
                </span>
              </div>

              {entry.details ? (
                <details className="log-entry__details">
                  <summary>{copy.details}</summary>
                  <pre>{entry.details}</pre>
                </details>
              ) : (
                <p className="helper-text">{copy.technicalEmpty}</p>
              )}
            </article>
          ))}
        </div>
      ) : null}
    </div>
  )
}
