/**
 * FormatBadge.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Displays the detected value format from the pipeline's format_detector.
 * Formats come from full_pipeline/utils/format_detector.py:
 *   ratio | percentage | date | currency | number | text
 *
 * Props:
 *   format:      string   — e.g. 'ratio', 'percentage', 'date', ...
 *   formatValid: bool     — whether extracted value matches expected format
 */

const FORMAT_CONFIG = {
  ratio: {
    label: 'Ratio',
    icon:  'ti-divide',
    color: '#4f46e5',
    bg:    'rgba(79,70,229,0.1)',
    example: '4.50 to 1.00',
  },
  percentage: {
    label: 'Pourcentage',
    icon:  'ti-percentage',
    color: '#0891b2',
    bg:    'rgba(8,145,178,0.1)',
    example: '2.25%',
  },
  date: {
    label: 'Date',
    icon:  'ti-calendar',
    color: '#059669',
    bg:    'rgba(5,150,105,0.1)',
    example: '2024-03-15',
  },
  currency: {
    label: 'Montant',
    icon:  'ti-currency-dollar',
    color: '#d97706',
    bg:    'rgba(217,119,6,0.1)',
    example: 'EUR 500,000',
  },
  number: {
    label: 'Nombre',
    icon:  'ti-123',
    color: '#7c3aed',
    bg:    'rgba(124,58,237,0.1)',
    example: '42',
  },
  text: {
    label: 'Texte',
    icon:  'ti-text-size',
    color: '#6b7280',
    bg:    'rgba(107,114,128,0.1)',
    example: 'Republic of Iraq',
  },
}

const FALLBACK = { label: 'Texte', icon: 'ti-text-size', color: '#6b7280', bg: 'rgba(107,114,128,0.1)' }

export default function FormatBadge({ format, formatValid }) {
  const cfg = FORMAT_CONFIG[format?.toLowerCase()] || FALLBACK

  return (
    <span
      title={`Format attendu : ${cfg.label}${cfg.example ? ` (ex: ${cfg.example})` : ''}`}
      style={{
        display:      'inline-flex',
        alignItems:   'center',
        gap:          4,
        padding:      '2px 8px',
        borderRadius: 20,
        fontSize:     11,
        fontWeight:   600,
        background:   cfg.bg,
        color:        cfg.color,
        whiteSpace:   'nowrap',
        cursor:       'default',
        position:     'relative',
      }}
    >
      <i className={`ti ${cfg.icon}`} style={{ fontSize: 11 }} />
      {cfg.label}
      {/* Format validation indicator */}
      {formatValid !== undefined && (
        <i
          className={`ti ${formatValid ? 'ti-check' : 'ti-x'}`}
          style={{
            fontSize: 10,
            color: formatValid ? '#16a34a' : '#dc2626',
          }}
          title={formatValid ? 'Format valide' : 'Format non conforme'}
        />
      )}
    </span>
  )
}
