import type {
  ContentSummaryResult,
  SubtitleAgentRequest,
  SubtitleQualityResult,
} from '../types/agent'
import { requestJson } from './backendClient'

export async function analyzeSubtitleQuality(
  request: SubtitleAgentRequest,
): Promise<SubtitleQualityResult> {
  return requestJson<SubtitleQualityResult>('/agent/subtitle-quality', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function summarizeSubtitleContent(
  request: SubtitleAgentRequest,
): Promise<ContentSummaryResult> {
  return requestJson<ContentSummaryResult>('/agent/content-summary', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}
