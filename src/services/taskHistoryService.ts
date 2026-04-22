import type {
  ImportResult,
} from '../types/import'
import type {
  LanguageCode,
  MediaType,
  ProjectFile,
  ProjectState,
  ProjectStatus,
  SubtitleSegment,
} from '../types/models'
import type {
  TaskEngineType,
  TaskHistoryRecord,
  TaskHistoryResponse,
  TaskLogEntry,
  TaskLogLevel,
  TaskMode,
  TaskStatus,
} from '../types/tasks'
import { requestJson } from './backendClient'

const VALID_TASK_MODES = new Set<TaskMode>(['extractAndTranslate', 'translateSubtitle'])
const VALID_TASK_ENGINE_TYPES = new Set<TaskEngineType>([
  'cloudTranscription',
  'localTranscription',
  'subtitleImport',
])
const VALID_TASK_STATUSES = new Set<TaskStatus>([
  'queued',
  'transcribing',
  'translating',
  'editing',
  'exporting',
  'done',
  'error',
  'cancelled',
])
const VALID_TASK_LOG_LEVELS = new Set<TaskLogLevel>(['info', 'warning', 'error'])
const VALID_PROJECT_STATUSES = new Set<ProjectStatus>([
  'idle',
  'transcribing',
  'translating',
  'exporting',
  'done',
  'error',
])
const VALID_MEDIA_TYPES = new Set<MediaType>(['video', 'audio', 'subtitle'])
const VALID_LANGUAGE_CODES = new Set<LanguageCode>(['auto', 'zh-CN', 'en', 'ja', 'ko'])

function readString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function readNullableString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.filter((item): item is string => typeof item === 'string')
}

function normalizeTaskLogEntry(value: unknown): TaskLogEntry | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const rawEntry = value as Partial<TaskLogEntry>
  const level = VALID_TASK_LOG_LEVELS.has(rawEntry.level as TaskLogLevel)
    ? (rawEntry.level as TaskLogLevel)
    : 'info'

  return {
    logId: readString(rawEntry.logId, `log-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`),
    timestamp: readString(rawEntry.timestamp, new Date().toISOString()),
    level,
    message: readString(rawEntry.message, 'LinguaSub restored an older task log entry.'),
    details: readNullableString(rawEntry.details),
  }
}

function normalizeLanguageCode(value: unknown, fallback: LanguageCode): LanguageCode {
  return VALID_LANGUAGE_CODES.has(value as LanguageCode)
    ? (value as LanguageCode)
    : fallback
}

function normalizeSubtitleSegment(value: unknown): SubtitleSegment | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const rawSegment = value as Partial<SubtitleSegment>
  const id = readString(rawSegment.id)
  if (!id) {
    return null
  }

  return {
    id,
    start: typeof rawSegment.start === 'number' ? rawSegment.start : 0,
    end:
      typeof rawSegment.end === 'number'
        ? rawSegment.end
        : typeof rawSegment.start === 'number'
          ? rawSegment.start
          : 0,
    sourceText: readString(rawSegment.sourceText),
    translatedText: readString(rawSegment.translatedText),
    sourceLanguage: normalizeLanguageCode(rawSegment.sourceLanguage, 'auto'),
    targetLanguage: normalizeLanguageCode(rawSegment.targetLanguage, 'zh-CN'),
  }
}

function normalizeProjectFile(value: unknown): ProjectFile | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const rawFile = value as Partial<ProjectFile>
  const path = readString(rawFile.path)
  const name = readString(rawFile.name)
  if (!path && !name) {
    return null
  }

  return {
    path,
    name: name || path.split(/[\\/]/).pop() || 'Untitled file',
    mediaType: VALID_MEDIA_TYPES.has(rawFile.mediaType as MediaType)
      ? (rawFile.mediaType as MediaType)
      : 'subtitle',
    extension: readString(rawFile.extension),
    requiresAsr:
      typeof rawFile.requiresAsr === 'boolean'
        ? rawFile.requiresAsr
        : rawFile.mediaType === 'video' || rawFile.mediaType === 'audio',
  }
}

function normalizeProjectState(value: unknown): ProjectState | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const rawProjectState = value as Partial<ProjectState>
  return {
    currentFile: normalizeProjectFile(rawProjectState.currentFile),
    segments: Array.isArray(rawProjectState.segments)
      ? rawProjectState.segments
          .map((segment) => normalizeSubtitleSegment(segment))
          .filter((segment): segment is SubtitleSegment => segment !== null)
      : [],
    status: VALID_PROJECT_STATUSES.has(rawProjectState.status as ProjectStatus)
      ? (rawProjectState.status as ProjectStatus)
      : 'idle',
    error: readNullableString(rawProjectState.error),
  }
}

function normalizeImportResult(value: unknown): ImportResult | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const rawImport = value as Partial<ImportResult>
  const currentFile = normalizeProjectFile(rawImport.currentFile)
  if (!currentFile) {
    return null
  }

  return {
    currentFile,
    projectState:
      normalizeProjectState(rawImport.projectState) ?? {
        currentFile,
        segments: [],
        status: 'idle',
        error: null,
      },
    workflow: readStringArray(rawImport.workflow),
    route:
      rawImport.route === 'recognition' || rawImport.route === 'translation'
        ? rawImport.route
        : 'translation',
    shouldSkipTranscription:
      typeof rawImport.shouldSkipTranscription === 'boolean'
        ? rawImport.shouldSkipTranscription
        : currentFile.mediaType === 'subtitle',
    recognitionInput:
      rawImport.recognitionInput &&
      typeof rawImport.recognitionInput === 'object' &&
      typeof rawImport.recognitionInput.mediaPath === 'string'
        ? {
            mediaPath: rawImport.recognitionInput.mediaPath,
            mediaType:
              rawImport.recognitionInput.mediaType === 'video' ||
              rawImport.recognitionInput.mediaType === 'audio'
                ? rawImport.recognitionInput.mediaType
                : 'audio',
            sourceLanguage: normalizeLanguageCode(
              rawImport.recognitionInput.sourceLanguage,
              'auto',
            ),
          }
        : null,
    subtitleInput:
      rawImport.subtitleInput &&
      typeof rawImport.subtitleInput === 'object' &&
      typeof rawImport.subtitleInput.subtitlePath === 'string'
        ? {
            subtitlePath: rawImport.subtitleInput.subtitlePath,
            parser: rawImport.subtitleInput.parser === 'srt' ? 'srt' : 'srt',
            encoding: readString(rawImport.subtitleInput.encoding, 'utf-8'),
          }
        : null,
  }
}

function normalizeTaskHistoryRecord(value: unknown): TaskHistoryRecord | null {
  if (!value || typeof value !== 'object') {
    return null
  }

  const rawTask = value as Partial<TaskHistoryRecord>
  const taskId = readString(rawTask.taskId)
  if (!taskId) {
    return null
  }

  const createdAt = readString(rawTask.createdAt, new Date().toISOString())
  const updatedAt = readString(rawTask.updatedAt, createdAt)
  const taskMode = VALID_TASK_MODES.has(rawTask.taskMode as TaskMode)
    ? (rawTask.taskMode as TaskMode)
    : 'extractAndTranslate'
  const engineType = VALID_TASK_ENGINE_TYPES.has(rawTask.engineType as TaskEngineType)
    ? (rawTask.engineType as TaskEngineType)
    : 'subtitleImport'
  const status = VALID_TASK_STATUSES.has(rawTask.status as TaskStatus)
    ? (rawTask.status as TaskStatus)
    : 'queued'

  return {
    taskId,
    sourceFilePath: readString(rawTask.sourceFilePath),
    sourceFileName: readString(rawTask.sourceFileName, 'Untitled task'),
    taskMode,
    sourceLanguage: readString(rawTask.sourceLanguage, 'auto'),
    targetLanguage: readString(rawTask.targetLanguage, 'zh'),
    outputFormats: readStringArray(rawTask.outputFormats),
    engineType,
    status,
    createdAt,
    updatedAt,
    exportPaths: readStringArray(rawTask.exportPaths),
    errorMessage: readNullableString(rawTask.errorMessage),
    subtitleSummary:
      rawTask.subtitleSummary &&
      typeof rawTask.subtitleSummary === 'object' &&
      typeof rawTask.subtitleSummary.segmentCount === 'number' &&
      typeof rawTask.subtitleSummary.translatedCount === 'number'
        ? {
            segmentCount: rawTask.subtitleSummary.segmentCount,
            translatedCount: rawTask.subtitleSummary.translatedCount,
          }
        : null,
    importSnapshot: normalizeImportResult(rawTask.importSnapshot),
    projectSnapshot: normalizeProjectState(rawTask.projectSnapshot),
    logs: Array.isArray(rawTask.logs)
      ? rawTask.logs
          .map((entry) => normalizeTaskLogEntry(entry))
          .filter((entry): entry is TaskLogEntry => entry !== null)
      : [],
    transcriptionProvider: readNullableString(rawTask.transcriptionProvider),
    transcriptionModelSize: readNullableString(rawTask.transcriptionModelSize),
    transcriptionQualityPreset: readNullableString(rawTask.transcriptionQualityPreset),
    translationProvider: readNullableString(rawTask.translationProvider),
    translationModel: readNullableString(rawTask.translationModel),
    outputMode: readNullableString(rawTask.outputMode),
  }
}

export async function loadTaskHistory(): Promise<TaskHistoryRecord[]> {
  const result = await requestJson<TaskHistoryResponse>('/tasks', {
    method: 'GET',
  })

  if (!result || !Array.isArray(result.tasks)) {
    console.error('LinguaSub task history payload is invalid.', result)
    return []
  }

  return result.tasks
    .map((task) => normalizeTaskHistoryRecord(task))
    .filter((task): task is TaskHistoryRecord => task !== null)
}

export async function upsertTaskHistoryRecord(
  task: TaskHistoryRecord,
): Promise<TaskHistoryRecord> {
  const result = await requestJson<{ task: TaskHistoryRecord }>('/tasks/upsert', {
    method: 'POST',
    body: JSON.stringify({ task }),
  })

  return normalizeTaskHistoryRecord(result.task) ?? task
}
