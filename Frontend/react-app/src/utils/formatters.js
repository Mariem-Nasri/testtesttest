/**
 * formatters.js
 * ──────────────────────────────────────────────────────────────────────────────
 * Utility functions for formatting data in the UI.
 */

/**
 * Format a date to a human-readable string.
 * @param {Date|string|null} date
 * @returns {string}
 */
export function formatDate(date) {
  if (!date) return '—'
  const d = new Date(date)
  if (isNaN(d)) return '—'
  return d.toLocaleDateString('fr-FR', {
    day:   '2-digit',
    month: 'short',
    year:  'numeric',
    hour:  '2-digit',
    minute:'2-digit',
  })
}

/**
 * Format a confidence score (0-1 or 0-100) to a percentage string.
 * @param {number|string} score
 * @returns {string}
 */
export function formatScore(score) {
  if (score === null || score === undefined || score === '') return '—'
  const n = parseFloat(score)
  if (isNaN(n)) return '—'
  const pct = n > 1 ? Math.round(n) : Math.round(n * 100)
  return `${pct}%`
}

/**
 * Format a file size in bytes to a human-readable string.
 * @param {number} bytes
 * @returns {string}
 */
export function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}

/**
 * Get the confidence level label from a score.
 * @param {number} score  — 0 to 1
 * @returns {'high'|'medium'|'low'}
 */
export function getConfidenceLevel(score) {
  const pct = score > 1 ? score : score * 100
  if (pct >= 80) return 'high'
  if (pct >= 50) return 'medium'
  return 'low'
}
