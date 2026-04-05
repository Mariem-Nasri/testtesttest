import { Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './components/layout/MainLayout'
import Login      from './pages/auth/Login'
import Dashboard  from './pages/Dashboard'
import Upload     from './pages/Upload'
import ExtractFields from './pages/ExtractFields'
import Documents  from './pages/Documents'
import Results    from './pages/Results'
import useAuthStore from './store/useAuthStore'

// ── Protected Route wrapper ──────────────────────────────────────────────────
function ProtectedRoute({ children }) {
  const { token } = useAuthStore()
  if (!token) return <Navigate to="/login" replace />
  return children
}

// ── App Routes ───────────────────────────────────────────────────────────────
export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />

      {/* Protected — wrapped inside MainLayout (sidebar + topbar) */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard"             element={<Dashboard />} />
        <Route path="upload"              element={<Upload />} />
        <Route path="extract-fields"      element={<ExtractFields />} />
        <Route path="documents"           element={<Documents />} />
        <Route path="documents/:id/results" element={<Results />} />
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
