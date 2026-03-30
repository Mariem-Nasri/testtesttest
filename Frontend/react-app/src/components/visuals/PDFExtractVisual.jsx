/**
 * PDFExtractVisual.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * After first render, measures the real pixel position of each HL row and
 * calculates the exact delay so the laser is AT that row when the bbox appears.
 * Guaranteed sync regardless of screen size or font scaling.
 */

import { useState, useEffect, useRef } from 'react'

const SCAN_DURATION = 5.2  // seconds — linear

const FIELDS = [
  { key: 0, label: 'Emprunteur',        value: 'VERMEG SA',   color: '#16a34a', textColor: '#bbf7d0' },
  { key: 1, label: 'Montant prêt',      value: '2 400 000 €', color: '#0284c7', textColor: '#bae6fd' },
  { key: 2, label: "Taux d'intérêt",    value: '4.75% / an',  color: '#7c3aed', textColor: '#ddd6fe' },
  { key: 3, label: 'Tableau (60 mois)', value: '60 mois',      color: '#b45309', textColor: '#fde68a' },
  { key: 4, label: 'Confiance agent',   value: '94.3%',        color: '#0891b2', textColor: '#a5f3fc' },
]

// Highlighted document row — border + bg animate via React state
function HL({ hlRef, idx, hl, children }) {
  const f = FIELDS[idx]
  const active = hl.has(idx)
  return (
    <div ref={hlRef} style={{
      position: 'relative',
      border: `1.5px solid ${active ? f.color : 'transparent'}`,
      borderRadius: 3,
      background: active ? `${f.color}14` : 'transparent',
      transition: 'border-color 0.2s ease, background 0.2s ease',
      padding: '3px 5px',
    }}>
      {active && (
        <div style={{
          position: 'absolute', top: -10, left: -1,
          background: f.color, color: '#fff',
          fontSize: 7, fontWeight: 700, letterSpacing: '0.2px',
          padding: '1px 5px', borderRadius: '2px 2px 0 0',
          whiteSpace: 'nowrap',
          animation: 'hl-in 0.18s ease both',
        }}>
          {f.label}
        </div>
      )}
      {children}
    </div>
  )
}

// Thin document-text line
function Line({ w = '100%', shade = 0.28, h = 2.5, mt = 0, mb = 3 }) {
  return (
    <div style={{
      height: h, width: w,
      background: `rgba(15,23,42,${shade})`,
      borderRadius: 2, marginTop: mt, marginBottom: mb,
    }} />
  )
}

export default function PDFExtractVisual() {
  const [hl,    setHl]    = useState(new Set())
  const [shown, setShown] = useState(new Set())
  const timers     = useRef([])
  const pdfBodyRef = useRef(null)
  const hlRefs     = useRef([])   // indexed 0-4

  useEffect(() => {
    let iv = null

    // Measure on first painted frame so offsetTop values are real
    const raf = requestAnimationFrame(() => {
      const body  = pdfBodyRef.current
      const bodyH = body?.offsetHeight || 0

      // Compute per-field delay: time when laser (linear, 5%-98%) is at the row centre
      const delays = FIELDS.map(f => {
        const el = hlRefs.current[f.key]
        if (!el || !bodyH) return 1 + f.key * 0.9  // sane fallback
        const centre = el.offsetTop + el.offsetHeight / 2
        const pct    = Math.max(0.06, Math.min(0.96, centre / bodyH))
        const t      = ((pct - 0.05) / 0.93) * SCAN_DURATION
        return Math.max(0.2, Math.round(t * 10) / 10)
      })

      function cycle() {
        timers.current.forEach(clearTimeout)
        timers.current = []
        setHl(new Set())
        setShown(new Set())
        delays.forEach((delay, i) => {
          const t = setTimeout(() => {
            setHl(prev   => new Set([...prev,   i]))
            setShown(prev => new Set([...prev, i]))
          }, delay * 1000)
          timers.current.push(t)
        })
      }

      cycle()
      iv = setInterval(cycle, (SCAN_DURATION + 2.2) * 1000)
    })

    return () => {
      cancelAnimationFrame(raf)
      clearInterval(iv)
      timers.current.forEach(clearTimeout)
    }
  }, [])

  return (
    <div style={{ userSelect: 'none', padding: '0 4px' }}>
      <style>{`
        @keyframes pe-scan {
          0%   { top: 5%;  opacity: 0 }
          4%   { opacity: 1 }
          94%  { opacity: 1 }
          100% { top: 98%; opacity: 0 }
        }
        @keyframes pe-dot-fly {
          0%   { left: 0%;   opacity: 0 }
          15%  { opacity: 1 }
          85%  { opacity: 1 }
          100% { left: 100%; opacity: 0 }
        }
        @keyframes pe-field-slide {
          from { opacity: 0.3; transform: translateX(-4px) }
          to   { opacity: 1;   transform: translateX(0) }
        }
        @keyframes pe-glow {
          0%, 100% { box-shadow: 0 0 10px rgba(0,200,100,0.2), 0 0 0 1.5px rgba(0,255,136,0.28) }
          50%       { box-shadow: 0 0 22px rgba(0,255,136,0.5), 0 0 0 1.5px rgba(0,255,136,0.6) }
        }
        @keyframes pe-title-glow {
          0%, 100% { text-shadow: 0 0 8px rgba(0,255,136,0.4) }
          50%       { text-shadow: 0 0 18px rgba(0,255,136,0.9) }
        }
        @keyframes hl-in {
          from { opacity: 0; transform: translateY(2px) }
          to   { opacity: 1; transform: translateY(0) }
        }
      `}</style>

      {/* Heading */}
      <div style={{
        textAlign: 'center', marginBottom: 14,
        fontSize: 12, fontWeight: 700, color: '#00ff99', letterSpacing: '0.4px',
        animation: 'pe-title-glow 3s ease-in-out infinite',
      }}>
        <i className="ti ti-scan me-2" style={{ fontSize: 13 }} />
        Extraction intelligente de champs
      </div>

      <div style={{ display: 'flex', alignItems: 'stretch', gap: 10 }}>

        {/* ── PDF card ─────────────────────────────────────────────── */}
        <div style={{
          flex: '0 0 43%', borderRadius: 11, overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          animation: 'pe-glow 3s ease-in-out infinite',
          position: 'relative',
        }}>
          {/* Browser-style toolbar */}
          <div style={{
            background: '#e2e8f0', borderBottom: '1px solid #cbd5e1',
            padding: '7px 10px', display: 'flex', alignItems: 'center', gap: 7,
            flexShrink: 0,
          }}>
            <div style={{ display: 'flex', gap: 4 }}>
              {['#f87171','#fbbf24','#34d399'].map(c => (
                <div key={c} style={{ width: 7, height: 7, borderRadius: '50%', background: c }} />
              ))}
            </div>
            <div style={{ flex: 1, background: '#fff', borderRadius: 4, padding: '2px 8px' }}>
              <span style={{ fontSize: 8, color: '#64748b', fontWeight: 600 }}>
                Accord_Prêt_2024.pdf
              </span>
            </div>
          </div>

          {/* White paper body */}
          <div ref={pdfBodyRef} style={{
            background: '#ffffff', flex: 1,
            padding: '12px 14px 14px', position: 'relative', overflow: 'hidden',
          }}>

            {/* Title */}
            <div style={{ textAlign: 'center', marginBottom: 8 }}>
              <Line w="55%" shade={0.75} h={4.5} mb={3} />
              <Line w="38%" shade={0.4}  h={3}   mb={0} />
            </div>
            <div style={{ height: 1, background: '#e2e8f0', margin: '7px 0 9px' }} />

            {/* Section 1 — Parties */}
            <div style={{ marginBottom: 10 }}>
              <Line w="32%" shade={0.65} h={3.5} mb={7} />
              <HL hlRef={el => { hlRefs.current[0] = el }} idx={0} hl={hl}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Line w="26%" shade={0.5} h={2.5} mb={0} />
                  <Line w="35%" shade={0.7} h={2.5} mb={0} />
                </div>
              </HL>
              <div style={{ marginTop: 4 }}>
                <Line w="72%" shade={0.22} h={2} mb={2} />
                <Line w="58%" shade={0.18} h={2} mb={0} />
              </div>
            </div>

            {/* Section 2 — Montant */}
            <div style={{ marginBottom: 10 }}>
              <Line w="28%" shade={0.65} h={3.5} mb={7} />
              <HL hlRef={el => { hlRefs.current[1] = el }} idx={1} hl={hl}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Line w="20%" shade={0.5} h={2.5} mb={0} />
                  <Line w="30%" shade={0.7} h={2.5} mb={0} />
                </div>
              </HL>
              <div style={{ marginTop: 4 }}>
                <Line w="65%" shade={0.2} h={2} mb={0} />
              </div>
            </div>

            {/* Section 3 — Table + Taux */}
            <div style={{ marginBottom: 10 }}>
              <Line w="34%" shade={0.65} h={3.5} mb={7} />
              <HL hlRef={el => { hlRefs.current[2] = el }} idx={2} hl={hl}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Line w="24%" shade={0.5} h={2.5} mb={0} />
                  <Line w="20%" shade={0.65} h={2.5} mb={0} />
                </div>
              </HL>
              <HL hlRef={el => { hlRefs.current[3] = el }} idx={3} hl={hl}>
                <div style={{
                  marginTop: 5, border: '1px solid #e2e8f0',
                  borderRadius: 3, overflow: 'hidden',
                }}>
                  <div style={{
                    background: '#f8fafc', borderBottom: '1px solid #e2e8f0',
                    padding: '3px 6px', display: 'flex', gap: 10,
                  }}>
                    <Line w="30%" shade={0.5}  h={2.5} mb={0} />
                    <Line w="22%" shade={0.5}  h={2.5} mb={0} />
                    <Line w="18%" shade={0.5}  h={2.5} mb={0} />
                  </div>
                  {[['38%','22%'],['42%','28%'],['35%','20%']].map(([c1,c2], ri) => (
                    <div key={ri} style={{
                      padding: '3px 6px', display: 'flex', gap: 10,
                      borderBottom: ri < 2 ? '1px solid #f1f5f9' : 'none',
                      background: ri % 2 === 0 ? '#fafafa' : '#fff',
                    }}>
                      <Line w={c1} shade={0.25} h={2} mb={0} />
                      <Line w={c2} shade={0.2}  h={2} mb={0} />
                    </div>
                  ))}
                </div>
              </HL>
            </div>

            {/* Section 4 — Validation */}
            <div>
              <Line w="30%" shade={0.65} h={3.5} mb={7} />
              <HL hlRef={el => { hlRefs.current[4] = el }} idx={4} hl={hl}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Line w="28%" shade={0.4} h={2.5} mb={0} />
                  <Line w="18%" shade={0.6} h={2.5} mb={0} />
                </div>
              </HL>
              <div style={{ marginTop: 4 }}>
                <Line w="70%" shade={0.18} h={2} mb={2} />
                <Line w="52%" shade={0.15} h={2} mb={0} />
              </div>
            </div>

            {/* Laser scan line — linear timing, duration synced to computed delays */}
            <div style={{
              position: 'absolute', left: 0, right: 0, height: 2,
              background: 'linear-gradient(90deg, transparent 0%, #00cc66 20%, #ffffff 50%, #00cc66 80%, transparent 100%)',
              animation: `pe-scan ${SCAN_DURATION}s linear infinite`,
              boxShadow: '0 0 12px rgba(0,220,100,0.9), 0 0 28px rgba(0,200,80,0.4)',
              zIndex: 20, pointerEvents: 'none',
            }} />
          </div>
        </div>

        {/* ── Arrow ─────────────────────────────────────────────────── */}
        <div style={{
          flex: '0 0 9%', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 3,
        }}>
          <div style={{ width: '100%', height: 2, background: 'rgba(0,255,136,0.2)', position: 'relative', borderRadius: 2 }}>
            {[0, 0.65, 1.3].map((d, i) => (
              <div key={i} style={{
                position: 'absolute', top: -2.5,
                width: 6, height: 6, borderRadius: '50%', background: '#00ff99',
                animation: 'pe-dot-fly 2.1s linear infinite',
                animationDelay: `${d}s`,
                boxShadow: '0 0 7px rgba(0,255,136,0.8)',
              }} />
            ))}
          </div>
          <div style={{
            marginTop: -3, width: 0, height: 0,
            borderTop: '5px solid transparent',
            borderBottom: '5px solid transparent',
            borderLeft: '8px solid rgba(0,255,136,0.65)',
          }} />
        </div>

        {/* ── Extracted fields ──────────────────────────────────────── */}
        <div style={{
          flex: '0 0 43%',
          background: 'linear-gradient(170deg, rgba(18,28,48,0.96), rgba(10,15,30,0.98))',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 11, padding: '10px',
          display: 'flex', flexDirection: 'column', gap: 5, overflow: 'hidden',
        }}>
          <div style={{
            fontSize: 8, fontWeight: 700, color: 'rgba(148,163,184,0.6)',
            textTransform: 'uppercase', letterSpacing: '0.9px',
            paddingBottom: 6, borderBottom: '1px solid rgba(255,255,255,0.06)',
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <i className="ti ti-braces" style={{ fontSize: 10 }} />
            Champs extraits
          </div>

          {FIELDS.map(f => {
            const active = shown.has(f.key)
            return (
              <div key={f.key} style={{
                padding: '5px 7px',
                background: active ? `${f.color}12` : 'rgba(255,255,255,0.02)',
                border: `1px solid ${active ? f.color + '40' : 'rgba(255,255,255,0.05)'}`,
                borderLeft: `2.5px solid ${active ? f.color : 'rgba(255,255,255,0.08)'}`,
                borderRadius: 5,
                display: 'flex', flexDirection: 'column', gap: 2,
                transition: 'all 0.3s ease',
                opacity: active ? 1 : 0.3,
                transform: active ? 'translateX(0)' : 'translateX(-4px)',
              }}>
                <span style={{ fontSize: 7.5, color: 'rgba(148,163,184,0.5)', fontWeight: 600 }}>
                  {f.label}
                </span>
                <span style={{
                  fontSize: 10.5, fontWeight: 700,
                  color: active ? f.textColor : 'rgba(148,163,184,0.2)',
                }}>
                  {f.value}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Tech badges */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
        {['DeepDoctection', 'DocTr OCR', 'Groq LLaMA'].map(t => (
          <span key={t} style={{
            fontSize: 8.5, fontWeight: 600,
            color: 'rgba(0,255,136,0.5)',
            background: 'rgba(0,255,136,0.05)',
            border: '1px solid rgba(0,255,136,0.12)',
            borderRadius: 4, padding: '2px 8px',
          }}>
            {t}
          </span>
        ))}
      </div>
    </div>
  )
}
