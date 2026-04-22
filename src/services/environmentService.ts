import type {
  StartupCheckReport,
  SpeechModelCleanupResult,
  SpeechModelDownloadStatus,
} from '../types/environment'
import type { AsrModelSize } from '../types/models'
import { requestJson } from './backendClient'

export type SpeechModelDownloadRequest = {
  modelSize: AsrModelSize
  storagePath: string | null
  rememberStoragePath: boolean
}

export async function loadEnvironmentCheck(): Promise<StartupCheckReport> {
  return requestJson<StartupCheckReport>('/environment/check')
}

export async function startSpeechModelDownload(
  request: SpeechModelDownloadRequest,
): Promise<SpeechModelDownloadStatus> {
  return requestJson<SpeechModelDownloadStatus>('/speech/models/download', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function cleanupSpeechModels(): Promise<SpeechModelCleanupResult> {
  return requestJson<SpeechModelCleanupResult>('/speech/models/cleanup', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}
