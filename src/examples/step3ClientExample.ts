import type { SubtitleSegment } from '../types/models'
import { loadConfig, updateConfig } from '../services/configService'
import { translateSegments } from '../services/translationService'

export async function exampleLoadAndUpdateConfig() {
  await loadConfig()

  return updateConfig({
    defaultProvider: 'deepseek',
    outputMode: 'bilingual',
    apiProviders: [
      {
        provider: 'deepseek',
        apiKey: 'your-deepseek-key',
        model: 'deepseek-chat',
      },
    ],
  })
}

export async function exampleTranslateSubtitleSegments() {
  const config = await loadConfig()

  const segments: SubtitleSegment[] = [
    {
      id: 'seg-001',
      start: 0,
      end: 2100,
      sourceText: 'Hello, everyone.',
      translatedText: '',
      sourceLanguage: 'en',
      targetLanguage: 'zh-CN',
    },
    {
      id: 'seg-002',
      start: 2100,
      end: 5200,
      sourceText: 'Welcome to LinguaSub.',
      translatedText: '',
      sourceLanguage: 'en',
      targetLanguage: 'zh-CN',
    },
  ]

  return translateSegments(segments, config)
}
