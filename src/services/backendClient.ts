const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8765'
const BACKEND_READY_TIMEOUT_MS = 12_000
const BACKEND_RETRY_DELAY_MS = 400

let backendReadyPromise: Promise<void> | null = null

export function getBackendUrl(): string {
  return import.meta.env.VITE_LINGUASUB_BACKEND_URL ?? DEFAULT_BACKEND_URL
}

function sleep(durationMs: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, durationMs)
  })
}

async function probeBackend(): Promise<boolean> {
  try {
    await fetch(`${getBackendUrl()}/environment/check`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    })

    return true
  } catch {
    return false
  }
}

async function waitForBackendReadyImpl(): Promise<void> {
  const deadline = Date.now() + BACKEND_READY_TIMEOUT_MS

  while (Date.now() < deadline) {
    if (await probeBackend()) {
      return
    }

    await sleep(BACKEND_RETRY_DELAY_MS)
  }

  throw new Error(
    'LinguaSub backend did not become ready in time. Please wait a moment and try again.',
  )
}

export async function ensureBackendReady(): Promise<void> {
  if (!backendReadyPromise) {
    backendReadyPromise = waitForBackendReadyImpl().catch((error) => {
      backendReadyPromise = null
      throw error
    })
  }

  await backendReadyPromise
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureBackendReady()

  let response: Response
  try {
    response = await fetch(`${getBackendUrl()}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
      ...init,
    })
  } catch {
    throw new Error(
      'Could not reach the LinguaSub backend. Please wait a moment and try again.',
    )
  }

  const rawBody = await response.text()
  let data: T | { error?: string } | null = null
  if (rawBody.trim()) {
    try {
      data = JSON.parse(rawBody) as T | { error?: string }
    } catch {
      if (!response.ok) {
        throw new Error(`Backend request failed with status ${response.status}.`)
      }
      throw new Error('LinguaSub backend returned an invalid response payload.')
    }
  }

  if (!response.ok) {
    const message =
      typeof data === 'object' && data !== null && 'error' in data
        ? data.error
        : `Backend request failed with status ${response.status}`
    throw new Error(message)
  }

  if (data === null) {
    throw new Error('LinguaSub backend returned an empty response.')
  }

  return data as T
}
