import type { SubtitleSegment } from './models'

export type VideoBurnExportMode = 'translated' | 'bilingual' | 'source'

export type VideoBurnExportRequest = {
  videoPath: string
  outputPath: string
  segments: SubtitleSegment[]
  mode: VideoBurnExportMode
}

export type VideoBurnExportResult = {
  outputPath: string
  directory: string
  fileName: string
  mode: VideoBurnExportMode
  count: number
  status: 'done'
  message: string
}
