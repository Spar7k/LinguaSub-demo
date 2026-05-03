import type { SubtitleSegment } from '../types/models'
import type {
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
