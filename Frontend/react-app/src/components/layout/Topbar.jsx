/**
 * Topbar.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Sticky top navigation bar.
 * Adapted from the Dasher template's topbar-second partial.
 * Shows breadcrumb, toggle button (mobile), and user controls.
 */

import { useLocation, Link } from 'react-router-dom'
import useLanguageStore from '../../store/useLanguageStore'

// ── Breadcrumb mapping ────────────────────────────────────────────────────────
const ROUTE_LABELS = {
  '/dashboard':  ['Dashboard'],
  '/upload':     ['Dashboard', 'Upload Document'],
  '/documents':  ['Dashboard', 'Documents'],
}

function getBreadcrumb(pathname) {
  // Handle dynamic routes like /documents/:id/results
  if (pathname.includes('/results')) {
    return ['Dashboard', 'Documents', 'Résultats']
  }
  return ROUTE_LABELS[pathname] || ['Dashboard']
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function Topbar({ onMenuToggle }) {
  const { pathname } = useLocation()
  const { language, toggleLanguage } = useLanguageStore()
  const crumbs       = getBreadcrumb(pathname)
  const pageTitle    = crumbs[crumbs.length - 1]

  const handleLanguageToggle = () => {
    console.log('Language toggle clicked. Current:', language)
    toggleLanguage()
  }

  return (
    <div className="topbar">
      {/* ── Left side: hamburger + breadcrumb ── */}
      <div className="topbar-left">
        {/* Mobile hamburger */}
        <button
          className="btn-icon-topbar d-lg-none"
          onClick={onMenuToggle}
          aria-label="Toggle sidebar"
        >
          <i className="ti ti-menu-2" />
        </button>

        <div>
          <h1 className="topbar-title">{pageTitle}</h1>
          {/* Breadcrumb */}
          <nav aria-label="breadcrumb">
            <ol className="breadcrumb mb-0" style={{ fontSize: 12 }}>
              {crumbs.map((crumb, idx) => {
                const isLast = idx === crumbs.length - 1
                return isLast ? (
                  <li key={crumb} className="breadcrumb-item active">
                    {crumb}
                  </li>
                ) : (
                  <li key={crumb} className="breadcrumb-item">
                    <Link to="/dashboard">{crumb}</Link>
                  </li>
                )
              })}
            </ol>
          </nav>
        </div>
      </div>

      {/* ── Right side: actions ── */}
      <div className="topbar-right">
        {/* New upload shortcut */}
        <Link to="/upload" className="btn btn-primary btn-sm d-none d-md-flex align-items-center gap-1">
          <i className="ti ti-plus" style={{ fontSize: 16 }} />
          Nouveau
        </Link>

        {/* Language toggle */}
        <button className="btn-icon-topbar" aria-label="Change language" onClick={handleLanguageToggle} title={language === 'fr' ? 'Switch to English' : 'Passer au français'}>
          <i className="ti ti-language" />
          <span style={{ fontSize: 11, fontWeight: 600, marginLeft: 4 }}>{language.toUpperCase()}</span>
        </button>

        {/* Notification bell */}
        <button className="btn-icon-topbar" aria-label="Notifications">
          <i className="ti ti-bell" />
          {/* Uncomment when notifications are implemented */}
          {/* <span className="notification-badge">3</span> */}
        </button>

        {/* Theme / settings placeholder */}
        <button className="btn-icon-topbar" aria-label="Settings">
          <i className="ti ti-settings" />
        </button>
      </div>
    </div>
  )
}
