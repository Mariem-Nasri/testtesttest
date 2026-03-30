/**
 * PageHeader.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Reusable page heading with title, subtitle and optional action button.
 *
 * Props:
 *   title:    string
 *   subtitle: string  (optional)
 *   action:   ReactNode  (optional — button/link placed top-right)
 */

export default function PageHeader({ title, subtitle, action }) {
  return (
    <div className="d-flex align-items-start justify-content-between mb-4 flex-wrap gap-3 page-header">
      <div>
        <h2 style={{
          fontSize: 22, fontWeight: 800, marginBottom: 4,
          background: 'linear-gradient(90deg, var(--text-primary), var(--primary))',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
        }}>
          {title}
        </h2>
        {subtitle && (
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>
            {subtitle}
          </p>
        )}
      </div>
      {action && <div>{action}</div>}
    </div>
  )
}
