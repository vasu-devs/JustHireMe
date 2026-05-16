import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import LeadsPage from './pages/LeadsPage.jsx'

export default function App() {
  return (
    <div style={{ minHeight: '100vh' }}>
      <Routes>
        <Route path="/" element={<Navigate to="/leads" replace />} />
        <Route path="/leads" element={<LeadsPage />} />
      </Routes>
    </div>
  )
}
