export interface CommandAgentContextSummary {
  videoName?: string
  videoPath?: string
  subtitleCount: number
  translatedCount: number
  translationCoverage: number
  sourceLanguage?: string
  targetLanguage?: string
  bilingualMode?: string
}

export interface CommandAgentResult {
  intent: string
  title: string
  summary: string
  content: string
  suggestedActions: string[]
  diagnostics?: Record<string, unknown>
}

export interface CommandAgentSessionItem {
  id: string
  instruction: string
  result: CommandAgentResult
  contextSummary: CommandAgentContextSummary
  segmentSignature?: string
  createdAt: string
}

export interface CommandAgentState {
  latestItem?: CommandAgentSessionItem
}
