import React from 'react'
import ReactDOM from 'react-dom/client'
import DecisionWorkbench from './DecisionWorkbench'
import './decision-workbench.css'

const root = document.getElementById('decision-workbench-root')
if (root) {
  ReactDOM.createRoot(root).render(<React.StrictMode><DecisionWorkbench /></React.StrictMode>)
}
