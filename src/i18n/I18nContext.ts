import { createContext } from 'react'

import { messages, type UiLanguage } from './messages'

export type I18nContextValue = {
  language: UiLanguage
  setLanguage: (language: UiLanguage) => void
  m: (typeof messages)[UiLanguage]
}

export const I18nContext = createContext<I18nContextValue | null>(null)
