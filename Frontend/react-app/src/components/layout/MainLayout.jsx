/**
 * MainLayout.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Root layout for authenticated pages.
 * Structure mirrors the Dasher template: Sidebar + #content wrapper.
 * Uses React Router's <Outlet /> to render child page components.
 */

import { useState } from 'react'
import { Outlet }   from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar  from './Topbar'

export default function MainLayout() {
  // Sidebar open/close state (used on mobile)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* ── Sidebar (fixed left) ── */}
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* ── Main content area ── */}
      <div id="content" style={{ flex: 1 }}>
        {/* Sticky top bar */}
        <Topbar onMenuToggle={() => setSidebarOpen(true)} />

        {/* Page content — rendered by React Router */}
        <div className="custom-container">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
