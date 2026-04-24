import { requestJson } from './backendClient'
import type {
  VideoBurnExportRequest,
  VideoBurnExportResult,
} from '../types/videoExport'

export async function exportBurnedSubtitleVideo(
  request: VideoBurnExportRequest,
): Promise<VideoBurnExportResult> {
  return requestJson<VideoBurnExportResult>('/video-subtitle/export-video', {
    method: 'POST',
    body: JSON.stringify({
      videoPath: request.videoPath,
      outputPath: request.outputPath,
      segments: request.segments,
      mode: request.mode,
    }),
  })
}
