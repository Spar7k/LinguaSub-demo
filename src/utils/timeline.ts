export function formatTimelineMs(value: number): string {
  if (!Number.isFinite(value) || value < 0) {
    return '--:--:--.---'
  }

  const normalized = Math.round(value)
  const totalSeconds = Math.floor(normalized / 1000)
  const milliseconds = normalized % 1000
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  return `${hours.toString().padStart(2, '0')}:${minutes
    .toString()
    .padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${milliseconds
    .toString()
    .padStart(3, '0')}`
}

