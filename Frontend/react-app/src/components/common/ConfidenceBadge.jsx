/**
 * ConfidenceBadge.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Displays an extraction confidence score as a coloured progress bar + %.
 *
 * Props:
 *   score: number  — 0 to 1  (e.g. 0.91 → 91%)
 *                 — OR 0 to 100
 */

export default function ConfidenceBadge({ score }) {
  // Normalise: accept 0-1 or 0-100
  const pct    = score > 1 ? Math.round(score) : Math.round(score * 100)
  const level  = pct >= 80 ? 'high' : pct >= 50 ? 'medium' : 'low'

  return (
    <div className="confidence-bar-wrap">
      <div className="confidence-bar-track">
        <div
          className={`confidence-bar-fill ${level}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`confidence-text ${level}`}>{pct}%</span>
    </div>
  )
}
