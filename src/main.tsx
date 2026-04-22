import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AppErrorBoundary } from './components/AppErrorBoundary.tsx'
import { I18nProvider } from './i18n/I18nProvider.tsx'

const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error('LinguaSub root container was not found.')
}

createRoot(rootElement).render(
  <StrictMode>
    <AppErrorBoundary>
      <I18nProvider>
        <App />
      </I18nProvider>
    </AppErrorBoundary>
  </StrictMode>,
)
