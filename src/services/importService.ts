import type { ImportResult } from '../types/import'
import { requestJson } from './backendClient'

export async function importFile(path: string): Promise<ImportResult> {
  console.info('[LinguaSub][Import] request:start', { path })
  const result = await requestJson<ImportResult>('/import', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })

  console.info('[LinguaSub][Import] request:success', {
    path,
    route: result.route,
    mediaType: result.currentFile.mediaType,
  })

  return result
}
