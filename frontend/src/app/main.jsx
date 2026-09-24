import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './app.css' // last, so the unified tokens win over the legacy stylesheet

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
