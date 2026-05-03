import type {
  CommandAgentResult,
  CommandAgentRunRequest,
} from '../types/commandAgent'
import { requestJson } from './backendClient'

const DEFAULT_COMMAND_AGENT_TIMEOUT_SECONDS = 60

export async function runCommandAgent({
  instruction,
  segments,
  config,
  context,
  timeoutSeconds = DEFAULT_COMMAND_AGENT_TIMEOUT_SECONDS,
}: CommandAgentRunRequest): Promise<CommandAgentResult> {
  return requestJson<CommandAgentResult>('/agent/command', {
    method: 'POST',
    body: JSON.stringify({
      instruction,
      segments,
      config,
      context,
      timeoutSeconds,
    }),
  })
}
