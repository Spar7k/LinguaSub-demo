import type { AsrModelSize, AppConfig, TranscriptionProviderName } from '../types/models'
import type {
  AsrInputLanguage,
  AsrQualityPreset,
  TranscribeMediaResponse,
} from '../types/transcription'
import { requestJson } from './backendClient'

export async function transcribeMedia(
  path: string,
  options: {
    provider: TranscriptionProviderName
    language?: AsrInputLanguage
    modelSize?: AsrModelSize
    qualityPreset?: AsrQualityPreset
    config?: AppConfig | null
  },
): Promise<TranscribeMediaResponse> {
  return requestJson<TranscribeMediaResponse>('/transcribe', {
    method: 'POST',
    body: JSON.stringify({
      path,
      provider: options.provider,
      language: options.language ?? 'auto',
      modelSize: options.modelSize ?? 'small',
      qualityPreset: options.qualityPreset ?? 'balanced',
      config: options.config ?? undefined,
    }),
  })
}
