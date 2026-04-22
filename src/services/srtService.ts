import type { LanguageCode, SubtitleSegment } from '../types/models'
import { requestJson } from './backendClient'

export type ParseSrtResponse = {
  segments: SubtitleSegment[]
  count: number
}

export async function parseSrt(
  path: string,
  sourceLanguage: LanguageCode = 'auto',
  targetLanguage: LanguageCode = 'zh-CN',
): Promise<ParseSrtResponse> {
  return requestJson<ParseSrtResponse>('/srt/parse', {
    method: 'POST',
    body: JSON.stringify({
      path,
      sourceLanguage,
      targetLanguage,
    }),
  })
}
