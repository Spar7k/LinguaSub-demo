import type { LanguageCode, MediaType, ProjectFile, ProjectState } from './models'

export type ImportRoute = 'recognition' | 'translation'

export type RecognitionInput = {
  mediaPath: string
  mediaType: Exclude<MediaType, 'subtitle'>
  sourceLanguage: LanguageCode
}

export type SubtitleParseInput = {
  subtitlePath: string
  parser: 'srt'
  encoding: string
}

export type ImportResult = {
  currentFile: ProjectFile
  projectState: ProjectState
  workflow: string[]
  route: ImportRoute
  shouldSkipTranscription: boolean
  recognitionInput: RecognitionInput | null
  subtitleInput: SubtitleParseInput | null
}
