import { useMemo } from 'react'

import { useI18n } from '../i18n/useI18n'
import type { TaskHistoryRecord } from '../types/tasks'

type RecentTasksPanelProps = {
  tasks: TaskHistoryRecord[]
  isLoading: boolean
  errorMessage: string | null
  onOpenTask: (task: TaskHistoryRecord) => void
  onRetryTask: (task: TaskHistoryRecord) => void
  onExportAgain: (task: TaskHistoryRecord) => void
  onOpenExportFolder: (task: TaskHistoryRecord) => void
}

function formatTimestamp(value: string): string {
  if (!value) {
    return '--'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function getStatusTone(status: TaskHistoryRecord['status']): string {
  if (status === 'done') {
    return 'success'
  }

  if (status === 'error' || status === 'cancelled') {
    return 'error'
  }

  if (status === 'transcribing' || status === 'translating' || status === 'exporting') {
    return 'warn'
  }

  return 'idle'
}

export function RecentTasksPanel({
  tasks,
  isLoading,
  errorMessage,
  onOpenTask,
  onRetryTask,
  onExportAgain,
  onOpenExportFolder,
}: RecentTasksPanelProps) {
  const { language } = useI18n()
  const safeTasks = Array.isArray(tasks) ? tasks : []
  const copy = useMemo(
    () =>
      language === 'zh'
        ? {
            title: '最近任务',
            description: '最近处理过的任务会保存在本地，重启应用后也能继续查看、重试或再次导出。',
            loadingTitle: '正在读取最近任务',
            loadingDescription: 'LinguaSub 正在恢复你最近的处理记录。',
            emptyTitle: '还没有历史任务',
            emptyDescription:
              '拖入视频或导入 SRT 后，这里会自动记录任务结果，方便回看和再次导出。',
            retry: '重试',
            openResult: '打开结果',
            exportAgain: '再次导出',
            openFolder: '打开文件夹',
            taskModes: {
              extractAndTranslate: '提取并翻译',
              translateSubtitle: '字幕翻译',
            },
            engineTypes: {
              cloudTranscription: '云端识别',
              localTranscription: '本地识别',
              subtitleImport: '导入字幕',
            },
            statuses: {
              queued: '已排队',
              transcribing: '处理中',
              translating: '处理中',
              editing: '可预览',
              exporting: '导出中',
              done: '已完成',
              error: '失败',
              cancelled: '已取消',
            },
            labels: {
              updatedAt: '最近更新',
              exportPath: '导出文件',
              summary: '字幕摘要',
              noExportPath: '还没有导出文件',
            },
            summary: (segments: number, translated: number) =>
              `${segments} 条字幕，${translated} 条已有译文`,
          }
        : {
            title: 'Recent tasks',
            description:
              'LinguaSub keeps your recent work on disk so you can reopen results, retry failed runs, and export again later.',
            loadingTitle: 'Loading recent tasks',
            loadingDescription: 'LinguaSub is restoring your recent work history.',
            emptyTitle: 'No task history yet',
            emptyDescription:
              'Import a video or an SRT file and LinguaSub will keep the result here for quick review and re-export.',
            retry: 'Retry',
            openResult: 'Open result',
            exportAgain: 'Export again',
            openFolder: 'Open folder',
            taskModes: {
              extractAndTranslate: 'Extract + translate',
              translateSubtitle: 'Subtitle translation',
            },
            engineTypes: {
              cloudTranscription: 'Cloud transcription',
              localTranscription: 'Local transcription',
              subtitleImport: 'Subtitle import',
            },
            statuses: {
              queued: 'Queued',
              transcribing: 'Processing',
              translating: 'Processing',
              editing: 'Preview ready',
              exporting: 'Exporting',
              done: 'Done',
              error: 'Failed',
              cancelled: 'Cancelled',
            },
            labels: {
              updatedAt: 'Updated',
              exportPath: 'Export file',
              summary: 'Subtitle summary',
              noExportPath: 'No export file yet',
            },
            summary: (segments: number, translated: number) =>
              `${segments} subtitle rows, ${translated} translated`,
          },
    [language],
  )

  return (
    <div className="recent-tasks">
      <div className="recent-tasks__header">
        <div>
          <h3>{copy.title}</h3>
          <p>{copy.description}</p>
        </div>
      </div>

      {isLoading ? (
        <div className="empty-state">
          <h3>{copy.loadingTitle}</h3>
          <p>{copy.loadingDescription}</p>
        </div>
      ) : null}

      {!isLoading && errorMessage ? (
        <div className="error-banner" role="alert">
          <strong>{copy.title}</strong>
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {!isLoading && !errorMessage && safeTasks.length === 0 ? (
        <div className="empty-state">
          <h3>{copy.emptyTitle}</h3>
          <p>{copy.emptyDescription}</p>
        </div>
      ) : null}

      {!isLoading && !errorMessage && safeTasks.length > 0 ? (
        <div className="recent-task-list">
          {safeTasks.map((task) => {
            const exportPath = Array.isArray(task.exportPaths) ? (task.exportPaths[0] ?? '') : ''
            const taskStatus = task.status ?? 'queued'
            const taskMode = task.taskMode ?? 'extractAndTranslate'
            const engineType = task.engineType ?? 'subtitleImport'
            const summary = task.subtitleSummary
              ? copy.summary(
                  task.subtitleSummary.segmentCount,
                  task.subtitleSummary.translatedCount,
                )
              : '--'

            return (
              <article key={task.taskId} className="recent-task-card">
                <div className="recent-task-card__head">
                  <div>
                    <strong>{task.sourceFileName || 'Untitled task'}</strong>
                    <p>
                      {copy.taskModes[taskMode]} / {copy.engineTypes[engineType]}
                    </p>
                  </div>
                  <span className={`status-pill status-pill--${getStatusTone(taskStatus)}`}>
                    {copy.statuses[taskStatus]}
                  </span>
                </div>

                <div className="summary-grid">
                  <div className="summary-item">
                    <span className="summary-item__label">{copy.labels.updatedAt}</span>
                    <span className="summary-item__value">{formatTimestamp(task.updatedAt)}</span>
                  </div>
                  <div className="summary-item">
                    <span className="summary-item__label">{copy.labels.summary}</span>
                    <span className="summary-item__value">{summary}</span>
                  </div>
                  <div className="summary-item">
                    <span className="summary-item__label">{copy.labels.exportPath}</span>
                    <span className="summary-item__value summary-item__value--wrap">
                      {exportPath || copy.labels.noExportPath}
                    </span>
                  </div>
                </div>

                {task.errorMessage ? (
                  <div className="warning-banner" role="alert">
                    <strong>{copy.statuses.error}</strong>
                    <p>{task.errorMessage}</p>
                  </div>
                ) : null}

                <div className="inline-actions">
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={() => onOpenTask(task)}
                  >
                    {copy.openResult}
                  </button>

                  {taskStatus === 'done' ? (
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => onExportAgain(task)}
                    >
                      {copy.exportAgain}
                    </button>
                  ) : null}

                  {taskStatus === 'error' ? (
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => onRetryTask(task)}
                    >
                      {copy.retry}
                    </button>
                  ) : null}

                  {exportPath ? (
                    <button
                      type="button"
                      className="button button--secondary"
                      onClick={() => onOpenExportFolder(task)}
                    >
                      {copy.openFolder}
                    </button>
                  ) : null}
                </div>
              </article>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
