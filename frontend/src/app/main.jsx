import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { installFetchAuth } from './auth'
import './app.css' // last, so the unified tokens win over the legacy stylesheet

installFetchAuth()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
