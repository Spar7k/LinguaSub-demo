import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { I18nContext } from './I18nContext'
import {
  UI_LANGUAGE_STORAGE_KEY,
  isUiLanguage,
  messages,
  type UiLanguage,
} from './messages'

function getInitialLanguage(): UiLanguage {
  if (typeof window === 'undefined') {
    return 'zh'
  }

  const storedValue = window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY)
  if (storedValue && isUiLanguage(storedValue)) {
    return storedValue
  }

  return 'zh'
}

type I18nProviderProps = {
  children: ReactNode
}

export function I18nProvider({ children }: I18nProviderProps) {
  const [language, setLanguage] = useState<UiLanguage>(getInitialLanguage)

  useEffect(() => {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language)
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en'
  }, [language])

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      m: messages[language],
    }),
    [language],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
