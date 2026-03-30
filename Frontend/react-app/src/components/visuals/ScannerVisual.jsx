/**
 * ScannerVisual.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Option 1 — "The Scanner"
 * 3D-tilted PDF document with a green laser scan line, bounding boxes that
 * appear sequentially with agent labels + extracted values, and mouse parallax.
 * Pure CSS animations — no extra dependencies.
 */

import { useRef, useCallback, useState } from 'react'

const FIELDS = [
  { top: 12, h: 7,  left: 6, w: 60, label: 'Emprunteur',       value: 'VERMEG SA',    color: '#00a76f', agent: 'A1', delay: 0.7 },
  { top: 24, h: 7,  left: 6, w: 50, label: 'Montant prêt',      value: '2 400 000 €',  color: '#2e86ab', agent: 'A2', delay: 1.2 },
  { top: 36, h: 7,  left: 6, w: 42, label: "Taux d'intérêt",    value: '4.75% / an',   color: '#00a76f', agent: 'A1', delay: 1.7 },
  { top: 48, h: 16, left: 6, w: 88, label: 'Tableau échéances',  value: '36 lignes',    color: '#7c3aed', agent: 'A2', delay: 2.2 },
  { top: 70, h: 7,  left: 6, w: 55, label: 'Score validation',   value: '94.3% conf.',  color: '#b45309', agent: 'A3', delay: 2.8 },
]

export default function ScannerVisual() {
  const ref = useRef(null)
  const [tilt, setTilt] = useState({ x: 10, y: -14 })

  const onMove = useCallback(e => {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const cx = (e.clientX - r.left) / r.width - 0.5
    const cy = (e.clientY - r.top) / r.height - 0.5
    setTilt({ x: -cy * 16, y: cx * 20 })
  }, [])

  const onLeave = useCallback(() => setTilt({ x: 10, y: -14 }), [])

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ perspective: 900, userSelect: 'none', padding: '4px 8px' }}
    >
      <style>{`
        @keyframes sv-scan {
          0%   { top: -2px; opacity: 0 }
          8%   { opacity: 1 }
          92%  { opacity: 1 }
          100% { top: calc(100% + 2px); opacity: 0 }
        }
        @keyframes sv-reveal {
          from { clip-path: inset(0 100% 0 0); opacity: 0 }
          to   { clip-path: inset(0 0% 0 0);  opacity: 1 }
        }
        @keyframes sv-fade {
          from { opacity: 0; transform: translateY(3px) }
          to   { opacity: 1; transform: translateY(0) }
        }
        @keyframes sv-blink {
          0%, 100% { opacity: 1 }
          50%       { opacity: 0.3 }
        }
      `}</style>

      {/* 3D PDF card */}
      <div style={{
        transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
        transformStyle: 'preserve-3d',
        transition: 'transform 0.1s ease-out',
        background: 'linear-gradient(160deg, rgba(13,20,38,0.97) 0%, rgba(7,11,22,0.99) 100%)',
        border: '1px solid rgba(0,167,111,0.3)',
        borderRadius: 14,
        padding: '14px',
        position: 'relative',
        overflow: 'hidden',
        boxShadow: [
          '0 32px 80px rgba(0,0,0,0.75)',
          '0 0 60px rgba(0,167,111,0.1)',
          'inset 0 1px 0 rgba(255,255,255,0.04)',
        ].join(', '),
        minHeight: 260,
      }}>

        {/* PDF top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          marginBottom: 10, paddingBottom: 8,
          borderBottom: '1px solid rgba(255,255,255,0.05)',
        }}>
          <div style={{
            width: 24, height: 24,
            background: 'rgba(0,167,111,0.1)',
            border: '1px solid rgba(0,167,111,0.2)',
            borderRadius: 5,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <i className="ti ti-file-text" style={{ fontSize: 11, color: '#00a76f' }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'rgba(226,232,240,0.85)' }}>
              Accord_de_Prêt_2024.pdf
            </div>
            <div style={{ fontSize: 9, color: 'rgba(148,163,184,0.45)' }}>Extraction en cours…</div>
          </div>
          <div style={{
            fontSize: 9, color: '#00a76f', fontWeight: 700,
            display: 'flex', alignItems: 'center', gap: 3,
          }}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%',
              background: '#00a76f', display: 'inline-block',
              animation: 'sv-blink 1.4s infinite',
            }} />
            LIVE
          </div>
        </div>

        {/* Background text lines (simulated document content) */}
        {[9, 16, 24, 34, 44, 56, 65, 73, 81, 88].map((top, i) => (
          <div key={i} style={{
            position: 'absolute',
            left: '5%', top: `${top}%`,
            height: 3.5,
            width: `${55 + (i * 13 % 38)}%`,
            background: `rgba(255,255,255,${i % 3 === 0 ? 0.03 : 0.018})`,
            borderRadius: 3,
          }} />
        ))}

        {/* Laser scan line */}
        <div style={{
          position: 'absolute', left: 0, right: 0, height: 2,
          background: 'linear-gradient(90deg, transparent 0%, #00a76f 25%, #00ff88 50%, #00a76f 75%, transparent 100%)',
          animation: 'sv-scan 3.2s ease-in-out infinite',
          boxShadow: '0 0 16px rgba(0,255,136,0.75), 0 0 40px rgba(0,167,111,0.4)',
          zIndex: 10,
        }} />

        {/* Bounding boxes */}
        {FIELDS.map((f, i) => (
          <div key={i} style={{
            position: 'absolute',
            left: `${f.left}%`, width: `${f.w}%`,
            top: `${f.top}%`, height: `${f.h}%`,
            border: `1.5px solid ${f.color}`,
            borderRadius: 3,
            background: `${f.color}10`,
            animation: 'sv-reveal 0.45s ease forwards',
            animationDelay: `${f.delay}s`,
            animationFillMode: 'both',
            zIndex: 5,
          }}>
            {/* Agent + field label tab */}
            <div style={{
              position: 'absolute', top: -9, left: 0,
              background: f.color, color: '#fff',
              fontSize: 8, fontWeight: 700,
              padding: '1px 4px', borderRadius: '2px 2px 0 0',
              animation: 'sv-fade 0.3s ease forwards',
              animationDelay: `${f.delay + 0.2}s`,
              animationFillMode: 'both',
              opacity: 0, whiteSpace: 'nowrap',
            }}>
              {f.agent} · {f.label}
            </div>

            {/* Extracted value chip */}
            <div style={{
              position: 'absolute', right: 4, top: '50%',
              transform: 'translateY(-50%)',
              background: 'rgba(7,11,22,0.92)',
              border: `1px solid ${f.color}35`,
              color: f.color, fontSize: 9, fontWeight: 700,
              padding: '2px 6px', borderRadius: 3,
              whiteSpace: 'nowrap',
              animation: 'sv-fade 0.3s ease forwards',
              animationDelay: `${f.delay + 0.3}s`,
              animationFillMode: 'both',
              opacity: 0,
            }}>
              {f.value}
            </div>
          </div>
        ))}

        {/* Bottom status bar */}
        <div style={{
          position: 'absolute', bottom: 8, left: 12, right: 12,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontSize: 8.5, color: 'rgba(148,163,184,0.45)' }}>conf. moy. 94.3%</span>
          <span style={{
            fontSize: 8.5, color: '#00a76f', fontWeight: 600,
            background: 'rgba(0,167,111,0.08)',
            border: '1px solid rgba(0,167,111,0.18)',
            borderRadius: 4, padding: '1px 6px',
          }}>
            DeepDoctection OCR
          </span>
        </div>
      </div>
    </div>
  )
}
