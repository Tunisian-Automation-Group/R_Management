import './polyfills.ts'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './app/App.tsx'
// Self-hosted, all axes (Archivo: weight and width; Bodoni Moda: weight and optical size).
import '@fontsource-variable/archivo/standard.css'
import '@fontsource-variable/bodoni-moda/standard.css'
import './app/theme.css'
import './app/theme.ts'
import { wireNative } from './native.ts'
import { reportClientError } from './data/repo.ts'
import { i18nReady } from './i18n.ts'

// What the ErrorBoundary cannot catch: event handlers, timers, promises (S-7).
window.addEventListener('error', (e) => reportClientError(e.error ?? e.message))
window.addEventListener('unhandledrejection', (e) => reportClientError(e.reason))

void wireNative()

// German readers wait for their strings rather than see English flash first.
void i18nReady.finally(() =>
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  ),
)
