import type { SubtitleSegment } from '../types/models'
import type { ExportFormat, ExportResult, WordExportMode } from '../types/export'
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
