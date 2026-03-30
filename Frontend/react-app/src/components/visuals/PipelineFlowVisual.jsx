/**
 * PipelineFlowVisual.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Option 2 — "The Pipeline Flow"
 * Horizontal animated pipeline: PDF → OCR → Router → Table → Validator → JSON.
 * Glowing nodes with staggered pulse, animated flowing dots on connectors.
 * Pure CSS animations — no extra dependencies.
 */

// Bright colors chosen to pop on the dark-green welcome banner background
const STEPS = [
  { label: 'PDF',       icon: 'ti-file-text',    color: '#ffffff', glow: 'rgba(255,255,255,0.5)', bg: 'rgba(255,255,255,0.12)' },
  { label: 'OCR',       icon: 'ti-scan',         color: '#7dd3fc', glow: 'rgba(125,211,252,0.6)', bg: 'rgba(125,211,252,0.12)' },
  { label: 'Router',    icon: 'ti-route',        color: '#86efac', glow: 'rgba(134,239,172,0.6)', bg: 'rgba(134,239,172,0.12)' },
  { label: 'Table',     icon: 'ti-table',        color: '#d8b4fe', glow: 'rgba(216,180,254,0.6)', bg: 'rgba(216,180,254,0.12)' },
  { label: 'Validator', icon: 'ti-shield-check', color: '#fde68a', glow: 'rgba(253,230,138,0.6)', bg: 'rgba(253,230,138,0.12)' },
  { label: 'JSON',      icon: 'ti-braces',       color: '#6ee7b7', glow: 'rgba(110,231,183,0.6)', bg: 'rgba(110,231,183,0.12)' },
]

export default function PipelineFlowVisual() {
  return (
    <div style={{
      padding: '14px 16px 10px',
      background: 'rgba(0,0,0,0.35)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderRadius: 14,
      border: '1px solid rgba(255,255,255,0.1)',
      width: '100%',
      position: 'relative', zIndex: 1,
    }}>
      <style>{`
        @keyframes pf-dot {
          0%   { left: -6px; opacity: 0 }
          12%  { opacity: 1 }
          88%  { opacity: 1 }
          100% { left: calc(100% + 6px); opacity: 0 }
        }
        @keyframes pf-glow {
          0%, 100% { opacity: 0.8; transform: scale(1) }
          50%       { opacity: 1;  transform: scale(1.07) }
        }
      `}</style>

      {/* Section label */}
      <div style={{
        fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.5)',
        textTransform: 'uppercase', letterSpacing: '1px',
        marginBottom: 12, textAlign: 'center',
      }}>
        Pipeline multi-agents
      </div>

      {/* Pipeline row */}
      <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
        {STEPS.map((s, i) => (
          <div key={s.label} style={{ display: 'flex', alignItems: 'center', flex: i < STEPS.length - 1 ? 1 : 0 }}>
            {/* Node */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, flexShrink: 0 }}>
              <div style={{
                width: 38, height: 38,
                background: s.bg,
                border: `1.5px solid ${s.color}80`,
                borderRadius: 11,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: s.color, fontSize: 17,
                boxShadow: `0 0 16px ${s.glow}`,
                animation: 'pf-glow 2.2s ease-in-out infinite',
                animationDelay: `${i * 0.36}s`,
              }}>
                <i className={`ti ${s.icon}`} />
              </div>
              <span style={{ fontSize: 8.5, fontWeight: 700, color: s.color, letterSpacing: '0.2px', whiteSpace: 'nowrap' }}>
                {s.label}
              </span>
            </div>

            {/* Connector + flowing dots */}
            {i < STEPS.length - 1 && (
              <div style={{
                flex: 1, height: 2,
                background: 'rgba(255,255,255,0.15)',
                position: 'relative',
                margin: '0 4px', marginBottom: 16,
              }}>
                {[0, 0.62, 1.24].map((offset, di) => (
                  <div key={di} style={{
                    position: 'absolute', top: -3,
                    width: 7, height: 7, borderRadius: '50%',
                    background: STEPS[i + 1].color,
                    animation: `pf-dot 1.8s linear infinite`,
                    animationDelay: `${i * 0.28 + offset}s`,
                    boxShadow: `0 0 8px ${STEPS[i + 1].glow}`,
                  }} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
