import { requestJson } from './backendClient'
import type {
  VideoSubtitleRunRequest,
  VideoSubtitleRunResponse,
} from '../types/videoSubtitle'

export async function runVideoSubtitle(
  request: VideoSubtitleRunRequest,
): Promise<VideoSubtitleRunResponse> {
  return requestJson<VideoSubtitleRunResponse>('/video-subtitle/run', {
    method: 'POST',
    body: JSON.stringify({
      videoPath: request.videoPath,
      subtitlePath: request.subtitlePath ?? undefined,
      sourceLanguage: request.sourceLanguage,
      outputMode: request.outputMode,
      config: request.config ?? undefined,
    }),
  })
}
