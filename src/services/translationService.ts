import type {
  AppConfig,
  ProviderName,
  SubtitleSegment,
} from '../types/models'
import { requestJson } from './backendClient'

export type TranslateSegmentsResponse = {
  segments: SubtitleSegment[]
  provider: ProviderName
  model: string
  baseUrl: string
  status: 'done'
}

export async function requestTranslation(
  segments: SubtitleSegment[],
  config: AppConfig,
): Promise<TranslateSegmentsResponse> {
  return requestJson<TranslateSegmentsResponse>('/translate', {
    method: 'POST',
    body: JSON.stringify({
      segments,
      config,
    }),
  })
}

export async function translateSegments(
  segments: SubtitleSegment[],
  config: AppConfig,
): Promise<SubtitleSegment[]> {
  const result = await requestTranslation(segments, config)
  return result.segments
}
