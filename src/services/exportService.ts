import type { SubtitleSegment } from '../types/models'
import type {
  CommandAgentWordExportRequest,
  CommandAgentWordExportResult,
  ContentSummaryWordExportRequest,
  ContentSummaryWordExportResult,
  ExportFormat,
  ExportResult,
  WordExportMode,
} from '../types/export'
import { requestJson } from './backendClient'

type ExportSubtitlesRequest = {
  segments: SubtitleSegment[]
  format?: ExportFormat
  bilingual?: boolean
  wordMode?: WordExportMode
  sourceFilePath?: string | null
  fileName?: string | null
}

export async function exportSubtitles({
  segments,
  format = 'srt',
  bilingual = true,
  wordMode = 'bilingualTable',
  sourceFilePath = null,
  fileName = null,
}: ExportSubtitlesRequest): Promise<ExportResult> {
  return requestJson<ExportResult>('/export', {
    method: 'POST',
    body: JSON.stringify({
      segments,
      format,
      bilingual,
      wordMode,
      sourceFilePath,
      fileName,
    }),
  })
}

export async function exportContentSummaryWord({
  summary,
  sourceFilePath = null,
  fileName = null,
}: ContentSummaryWordExportRequest): Promise<ContentSummaryWordExportResult> {
  return requestJson<ContentSummaryWordExportResult>('/export/content-summary-word', {
    method: 'POST',
    body: JSON.stringify({
      summary,
      sourceFilePath,
      fileName,
    }),
  })
}

export async function exportCommandAgentWord({
  instruction,
  result,
  contextSummary,
  createdAt,
  sourceFilePath,
  fileName = null,
}: CommandAgentWordExportRequest): Promise<CommandAgentWordExportResult> {
  return requestJson<CommandAgentWordExportResult>('/export/command-agent-word', {
    method: 'POST',
    body: JSON.stringify({
      instruction,
      result,
      contextSummary,
      createdAt,
      sourceFilePath,
      fileName,
    }),
  })
}
