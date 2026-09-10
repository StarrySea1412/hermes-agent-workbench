import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import QueryProvider from './providers/QueryProvider.jsx'
import { ToastProvider } from './components/Toast/index.jsx'
import { applyTheme, getTheme } from './theme.js'

applyTheme(getTheme())

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <QueryProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </QueryProvider>
    </BrowserRouter>
  </StrictMode>,
)