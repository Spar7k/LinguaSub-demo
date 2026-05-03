import { ensureBackendReady, getBackendUrl } from './backendClient'
import type {
  VideoBurnExportRequest,
  VideoBurnExportResult,
} from '../types/videoExport'

export class VideoBurnExportConnectionError extends Error {
  constructor() {
    super('Video export connection was interrupted.')
    this.name = 'VideoBurnExportConnectionError'
  }
}

export async function exportBurnedSubtitleVideo(
  request: VideoBurnExportRequest,
): Promise<VideoBurnExportResult> {
  await ensureBackendReady()

  let response: Response
  try {
    response = await fetch(`${getBackendUrl()}/video-subtitle/export-video`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        videoPath: request.videoPath,
        outputPath: request.outputPath,
        segments: request.segments,
        mode: request.mode,
      }),
    })
  } catch {
    throw new VideoBurnExportConnectionError()
  }

  const rawBody = await response.text()
  let data: VideoBurnExportResult | { error?: string } | null = null
  if (rawBody.trim()) {
    try {
      data = JSON.parse(rawBody) as VideoBurnExportResult | { error?: string }
    } catch {
      if (!response.ok) {
        throw new Error(`Backend request failed with status ${response.status}.`)
      }
      throw new Error('LinguaSub backend returned an invalid video export response.')
    }
  }

  if (!response.ok) {
    const message =
      typeof data === 'object' && data !== null && 'error' in data
        ? data.error
        : `Video export failed with status ${response.status}`
    throw new Error(message)
  }

  if (data === null) {
    throw new Error('LinguaSub backend returned an empty video export response.')
  }

  return data as VideoBurnExportResult
}
