import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import { applyColorScheme, getColorScheme } from './auth'

applyColorScheme(getColorScheme()) // 渲染前先落地缓存的涨跌配色,防止闪色

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
