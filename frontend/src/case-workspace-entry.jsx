import React from 'react'
import ReactDOM from 'react-dom/client'
import CaseWorkspace from './CaseWorkspace'

const root = document.getElementById('case-workspace-root')
if (root) {
  ReactDOM.createRoot(root).render(<React.StrictMode><CaseWorkspace /></React.StrictMode>)
}
