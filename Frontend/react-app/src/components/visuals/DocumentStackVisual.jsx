/**
 * DocumentStackVisual.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Option 3 — "The Document Stack"
 * Three stacked PDF pages at different Z-depths in 3D perspective.
 * The front page has animated bounding boxes; floating data chips orbit around.
 * Mouse parallax tilt on the whole stack.
 * Pure CSS animations — no extra dependencies.
 */

import { useRef, useCallback, useState } from 'react'

const BOXES = [
  { top: 16, left: 7, w: 52, h: 8,  color: '#00a76f', delay: 0.5, label: 'Emprunteur' },
  { top: 30, left: 7, w: 38, h: 8,  color: '#2e86ab', delay: 1.0, label: 'Montant'    },
  { top: 44, left: 7, w: 62, h: 16, color: '#7c3aed', delay: 1.5, label: 'Tableau'    },
  { top: 66, left: 7, w: 45, h: 8,  color: '#b45309', delay: 2.1, label: 'Validé'     },
]

const CHIPS = [
  { label: 'Loan Number', value: 'P-IQ-9240',    color: '#00a76f', top: '6%',  left: '63%', floatDelay: '0s'    },
  { label: 'Montant',     value: '€ 500 000 000', color: '#2e86ab', top: '26%', left: '66%', floatDelay: '0.8s'  },
  { label: 'Taux',        value: '6M-SOFR+0.7%',  color: '#7c3aed', top: '48%', left: '62%', floatDelay: '1.6s'  },
  { label: 'Validé',      value: '94.3% conf.',    color: '#b45309', top: '70%', left: '64%', floatDelay: '2.4s'  },
]

// Builds a ghost page (back / middle layers)
function GhostPage({ opacity, tx, ty, rx, ry }) {
  return (
    <div style={{
      position: 'absolute', top: 0, left: 0,
      width: '60%', height: '100%',
      background: `linear-gradient(160deg, rgba(13,20,38,${opacity}) 0%, rgba(7,11,22,${Math.min(opacity + 0.02, 1)}) 100%)`,
      border: `1px solid rgba(0,167,111,${(opacity * 0.55).toFixed(2)})`,
      borderRadius: 12,
      transform: `rotateX(${rx}deg) rotateY(${ry}deg) translate(${tx}px, ${ty}px)`,
      pointerEvents: 'none',
    }} />
  )
}

export default function DocumentStackVisual() {
  const ref = useRef(null)
  const [tilt, setTilt] = useState({ x: 8, y: 12 })

  const onMove = useCallback(e => {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const cx = (e.clientX - r.left) / r.width - 0.5
    const cy = (e.clientY - r.top) / r.height - 0.5
    setTilt({ x: -cy * 14, y: cx * 18 })
  }, [])

  const onLeave = useCallback(() => setTilt({ x: 8, y: 12 }), [])

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ perspective: 1100, userSelect: 'none', height: 240, position: 'relative' }}
    >
      <style>{`
        @keyframes ds-reveal {
          from { clip-path: inset(0 100% 0 0); opacity: 0 }
          to   { clip-path: inset(0 0% 0 0);  opacity: 1 }
        }
        @keyframes ds-chip-in {
          from { opacity: 0 }
          to   { opacity: 1 }
        }
        @keyframes ds-float {
          0%, 100% { transform: translateY(0px) }
          50%       { transform: translateY(-6px) }
        }
        @keyframes ds-blink {
          0%, 100% { opacity: 1 }
          50%       { opacity: 0.35 }
        }
      `}</style>

      {/* Page 3 — furthest back */}
      <GhostPage opacity={0.22} tx={22} ty={18} rx={4} ry={13} />

      {/* Page 2 — middle */}
      <GhostPage opacity={0.44} tx={11} ty={9}  rx={2} ry={7}  />

      {/* Page 1 — front (interactive) */}
      <div style={{
        position: 'absolute', top: 0, left: 0,
        width: '60%', height: '100%',
        background: 'linear-gradient(160deg, rgba(13,20,38,0.97) 0%, rgba(7,11,22,0.99) 100%)',
        border: '1px solid rgba(0,167,111,0.32)',
        borderRadius: 12,
        transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
        transition: 'transform 0.1s ease-out',
        boxShadow: [
          '0 28px 70px rgba(0,0,0,0.72)',
          '0 0 50px rgba(0,167,111,0.1)',
          'inset 0 1px 0 rgba(255,255,255,0.04)',
        ].join(', '),
        overflow: 'hidden',
        transformStyle: 'preserve-3d',
      }}>
        {/* PDF header */}
        <div style={{
          padding: '9px 12px',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <i className="ti ti-file-text" style={{ fontSize: 12, color: '#00a76f' }} />
          <span style={{ fontSize: 9.5, fontWeight: 700, color: 'rgba(226,232,240,0.82)' }}>
            Accord_de_Prêt_2024.pdf
          </span>
          <div style={{ marginLeft: 'auto', fontSize: 8.5, color: '#00a76f', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 3 }}>
            <span style={{ width: 4, height: 4, borderRadius: '50%', background: '#00a76f', display: 'inline-block', animation: 'ds-blink 1.5s infinite' }} />
            OCR
          </div>
        </div>

        {/* Background text lines */}
        {[14, 23, 33, 43, 55, 67, 77, 87].map((top, i) => (
          <div key={i} style={{
            position: 'absolute', left: '5%', top: `${top}%`,
            height: 3.5, width: `${50 + (i * 14 % 40)}%`,
            background: `rgba(255,255,255,${i % 3 === 0 ? 0.03 : 0.018})`,
            borderRadius: 3,
          }} />
        ))}

        {/* Animated bounding boxes */}
        {BOXES.map((b, i) => (
          <div key={i} style={{
            position: 'absolute',
            left: `${b.left}%`, width: `${b.w}%`,
            top: `${b.top}%`, height: `${b.h}%`,
            border: `1.5px solid ${b.color}`,
            borderRadius: 3,
            background: `${b.color}0f`,
            animation: 'ds-reveal 0.45s ease forwards',
            animationDelay: `${b.delay}s`,
            animationFillMode: 'both',
            zIndex: 5,
          }}>
            <div style={{
              position: 'absolute', top: -9, left: 0,
              background: b.color, color: '#fff',
              fontSize: 7.5, fontWeight: 700,
              padding: '1px 4px', borderRadius: '2px 2px 0 0',
              animation: 'ds-chip-in 0.3s ease forwards',
              animationDelay: `${b.delay + 0.2}s`,
              animationFillMode: 'both',
              opacity: 0, whiteSpace: 'nowrap',
            }}>
              {b.label}
            </div>
          </div>
        ))}
      </div>

      {/* Floating extracted-value chips */}
      {CHIPS.map((c, i) => (
        <div key={i} style={{
          position: 'absolute',
          left: c.left, top: c.top,
          animation: `ds-chip-in 0.4s ease forwards`,
          animationDelay: `${i * 0.5 + 1.2}s`,
          animationFillMode: 'both',
          opacity: 0,
        }}>
          <div style={{
            animation: `ds-float 3s ease-in-out infinite ${c.floatDelay}`,
            background: 'rgba(10,15,30,0.9)',
            border: `1px solid ${c.color}40`,
            borderRadius: 7, padding: '5px 10px',
            display: 'flex', flexDirection: 'column', gap: 2,
            boxShadow: `0 4px 20px rgba(0,0,0,0.5), 0 0 12px ${c.color}18`,
          }}>
            <span style={{ fontSize: 8, color: 'rgba(148,163,184,0.6)', fontWeight: 600 }}>
              {c.label}
            </span>
            <span style={{ fontSize: 9.5, color: c.color, fontWeight: 700, whiteSpace: 'nowrap' }}>
              {c.value}
            </span>
          </div>
        </div>
      ))}

      {/* Page counter badge */}
      <div style={{
        position: 'absolute', bottom: 4, left: '1%',
        fontSize: 8.5, color: 'rgba(148,163,184,0.4)', fontWeight: 500,
      }}>
        3 pages analysées
      </div>
    </div>
  )
}
