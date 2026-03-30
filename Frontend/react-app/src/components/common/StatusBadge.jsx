/**
 * StatusBadge.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Pill badge for document processing status.
 *
 * Props:
 *   status: 'completed' | 'processing' | 'error' | 'pending'
 */

const STATUS_CONFIG = {
  completed:  { label: 'Terminé',    variant: 'success',   icon: 'ti-check' },
  processing: { label: 'En cours',   variant: 'warning',   icon: 'ti-loader-2', spin: true },
  error:      { label: 'Erreur',     variant: 'danger',    icon: 'ti-alert-circle' },
  pending:    { label: 'En attente', variant: 'secondary', icon: 'ti-clock' },
}

export default function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending

  return (
    <span className={`status-badge ${cfg.variant}`}>
      {/* Spinning dot for processing, static dot for others */}
      {cfg.spin ? (
        <span className="status-dot spin" />
      ) : (
        <span className={`status-dot ${cfg.variant}`} />
      )}
      {cfg.label}
    </span>
  )
}
