/**
 * Sidebar.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Vertical navigation sidebar adapted from the Dasher Bootstrap template.
 * Uses React Router's NavLink for active-state highlighting.
 */

import { NavLink, useNavigate } from 'react-router-dom'
import useAuthStore from '../../store/useAuthStore'
import { useTranslation } from '../../hooks/useTranslation'

// ── Component ─────────────────────────────────────────────────────────────────
export default function Sidebar({ isOpen, onClose }) {
  const navigate   = useNavigate()
  const { t }      = useTranslation()
  const { user, logout } = useAuthStore()

  // Navigation items with translations
  const NAV_ITEMS = [
    {
      label: 'MAIN',
      items: [
        { to: '/dashboard', icon: 'ti-layout-dashboard', text: t('dashboard') },
        { to: '/upload',    icon: 'ti-cloud-upload',     text: t('uploadDocument') },
        { to: '/documents', icon: 'ti-files',            text: t('documents') },
      ],
    },
  ]

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <>
      {/* Mobile overlay — closes sidebar on click */}
      {isOpen && (
        <div
          className="d-lg-none"
          onClick={onClose}
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.45)',
            zIndex: 1049,
          }}
        />
      )}

      {/* Sidebar panel */}
      <div id="miniSidebar" className={isOpen ? 'open' : ''}>

        {/* ── Brand Logo ── */}
        <div className="brand-logo">
          <div className="logo-icon">
            <i className="ti ti-brain" />
          </div>
          <div>
            <span className="site-logo-text">DocAI</span>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', marginTop: 1 }}>
              Platform
            </div>
          </div>
        </div>

        {/* ── Navigation ── */}
        <ul className="sidebar-nav">
          {NAV_ITEMS.map((section) => (
            <div key={section.label}>
              {/* Section label */}
              <div className="nav-section-label">{section.label}</div>

              {/* Nav links */}
              {section.items.map((item) => (
                <li key={item.to} className="nav-item">
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      'nav-link' + (isActive ? ' active' : '')
                    }
                    onClick={() => onClose && onClose()}
                  >
                    <span className="nav-icon">
                      <i className={`ti ${item.icon}`} />
                    </span>
                    <span>{item.text}</span>
                  </NavLink>
                </li>
              ))}
            </div>
          ))}

          {/* ── Separator ── */}
          <li style={{ margin: '12px 10px' }}>
            <hr style={{ borderColor: 'rgba(255,255,255,0.08)', margin: 0 }} />
          </li>

          {/* ── System items ── */}
          <li className="nav-item">
            <button className="nav-link" onClick={handleLogout}>
              <span className="nav-icon">
                <i className="ti ti-logout" />
              </span>
              <span>{t('logout')}</span>
            </button>
          </li>
        </ul>

        {/* ── User area (bottom) ── */}
        <div className="sidebar-user">
          <div className="user-avatar">
            {user?.name?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="user-info">
            <div className="user-name">{user?.name || 'Utilisateur'}</div>
            <div className="user-role">{user?.role || 'Intern'}</div>
          </div>
        </div>
      </div>
    </>
  )
}
