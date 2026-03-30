/**
 * PipelineStats.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Pipeline execution statistics panel.
 * Displays confidence distribution (high/medium/low) and per-agent timing.
 *
 * Data mirrors the global stats computed in run_pipeline.py (lines 453–467):
 *   high_confidence   (score ≥ 0.8)
 *   medium_confidence (0.6 ≤ score < 0.8)
 *   low_confidence    (score < 0.6)
 *   total_llm_calls
 *   avg_llm_per_key
 *   keys_no_llm
 *   timing per agent
 *
 * Props:
 *   stats: {
 *     total_keys,
 *     high_confidence, medium_confidence, low_confidence,
 *     total_llm_calls, avg_llm_per_key, keys_no_llm,
 *     timing: { ocr, indexing, agent1, agent2, agent3, agent4 }
 *   }
 */

// ── Mini stat card (local) ────────────────────────────────────────────────────
function StatMini({ label, value, color, icon }) {
  return (
    <div style={{
      flex: 1, minWidth: 110,
      padding: '12px 14px',
      background: 'rgba(255,255,255,0.04)',
      border: '1px solid var(--border-color)',
      borderRadius: 10,
      borderTop: `3px solid ${color}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <i className={`ti ${icon}`} style={{ fontSize: 16, color }} />
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          {label}
        </span>
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>{value ?? '—'}</div>
    </div>
  )
}

// ── Timing bar ────────────────────────────────────────────────────────────────
function TimingBar({ label, icon, color, ms, maxMs }) {
  const pct = maxMs > 0 ? Math.round((ms / maxMs) * 100) : 0
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <i className={`ti ${icon}`} style={{ fontSize: 14, color }} />
          {label}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {ms != null ? `${ms.toFixed ? ms.toFixed(0) : ms} ms` : '—'}
        </span>
      </div>
      <div style={{ height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.5s ease' }} />
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function PipelineStats({ stats }) {
  if (!stats) return null

  const {
    total_keys = 0,
    high_confidence   = 0,
    medium_confidence = 0,
    low_confidence    = 0,
    total_llm_calls   = 0,
    keys_no_llm       = 0,
    timing            = {},
  } = stats

  // Confidence distribution percentages
  const highPct   = total_keys > 0 ? Math.round((high_confidence / total_keys) * 100)   : 0
  const medPct    = total_keys > 0 ? Math.round((medium_confidence / total_keys) * 100)  : 0
  const lowPct    = total_keys > 0 ? Math.round((low_confidence / total_keys) * 100)     : 0

  // Max timing for scaling bars
  const timingValues = Object.values(timing).filter(Boolean)
  const maxMs = timingValues.length > 0 ? Math.max(...timingValues) : 1

  const TIMING_STEPS = [
    { key: 'ocr',       label: 'OCR (DeepDoctection)', icon: 'ti-scan',         color: '#2e86ab' },
    { key: 'indexing',  label: 'Indexation embeddings', icon: 'ti-database',    color: '#7c3aed' },
    { key: 'agent1',    label: 'Agent 1 — Router',      icon: 'ti-route',       color: '#1d6fa0' },
    { key: 'agent2',    label: 'Agent 2 — Table',        icon: 'ti-table',      color: '#7c3aed' },
    { key: 'agent3',    label: 'Agent 3 — Validator',    icon: 'ti-shield-check',color: '#b45309' },
    { key: 'agent4',    label: 'Agent 4 — Définitions',  icon: 'ti-book',       color: '#007a52' },
  ]

  return (
    <div>
      {/* ── Top KPIs ── */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
        <StatMini label="Total champs"       value={total_keys}       color="var(--primary)"   icon="ti-list" />
        <StatMini label="Haute confiance"    value={`${high_confidence} (${highPct}%)`}   color="var(--success)"  icon="ti-circle-check" />
        <StatMini label="Confiance moyenne"  value={`${medium_confidence} (${medPct}%)`}  color="var(--warning)"  icon="ti-alert-circle" />
        <StatMini label="Faible confiance"   value={`${low_confidence} (${lowPct}%)`}     color="var(--danger)"   icon="ti-circle-x" />
        <StatMini label="Appels LLM"         value={total_llm_calls}  color="#7c3aed"          icon="ti-brain" />
        <StatMini label="Sans LLM (rapide)"  value={keys_no_llm}      color="#059669"           icon="ti-bolt" />
      </div>

      <div className="row g-4">
        {/* ── Confidence distribution bar ── */}
        <div className="col-md-5">
          <div className="card h-100">
            <div className="card-header d-flex align-items-center gap-2" style={{ fontSize: 13 }}>
              <i className="ti ti-chart-bar text-primary-app" />
              Distribution des scores de confiance
            </div>
            <div className="card-body">
              {/* Stacked bar */}
              <div style={{ display: 'flex', height: 28, borderRadius: 8, overflow: 'hidden', marginBottom: 14 }}>
                {highPct > 0 && (
                  <div title={`Haute confiance : ${high_confidence} champs`} style={{ flex: highPct, background: 'var(--success)', transition: 'flex 0.5s' }} />
                )}
                {medPct > 0 && (
                  <div title={`Confiance moyenne : ${medium_confidence} champs`} style={{ flex: medPct, background: 'var(--warning)', transition: 'flex 0.5s' }} />
                )}
                {lowPct > 0 && (
                  <div title={`Faible confiance : ${low_confidence} champs`} style={{ flex: lowPct, background: 'var(--danger)', transition: 'flex 0.5s' }} />
                )}
                {total_keys === 0 && (
                  <div style={{ flex: 1, background: 'rgba(255,255,255,0.08)' }} />
                )}
              </div>

              {/* Legend */}
              {[
                { label: 'Haute (≥ 80%)',    count: high_confidence,   pct: highPct,  color: 'var(--success)' },
                { label: 'Moyenne (50–79%)', count: medium_confidence, pct: medPct,   color: 'var(--warning)' },
                { label: 'Faible (< 50%)',   count: low_confidence,    pct: lowPct,   color: 'var(--danger)'  },
              ].map(row => (
                <div key={row.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: row.color }} />
                    <span style={{ fontSize: 13 }}>{row.label}</span>
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{row.count} <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>({row.pct}%)</span></span>
                </div>
              ))}

              {/* LLM usage */}
              <hr style={{ borderColor: 'var(--border-color)', margin: '14px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: 'var(--text-secondary)' }}>Appels LLM total</span>
                <span style={{ fontWeight: 600, color: '#7c3aed' }}>{total_llm_calls}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginTop: 6 }}>
                <span style={{ color: 'var(--text-secondary)' }}>Extraction sans LLM (embedding seul)</span>
                <span style={{ fontWeight: 600, color: 'var(--success)' }}>{keys_no_llm}</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Per-agent timing ── */}
        <div className="col-md-7">
          <div className="card h-100">
            <div className="card-header d-flex align-items-center gap-2" style={{ fontSize: 13 }}>
              <i className="ti ti-clock text-primary-app" />
              Temps d'exécution par étape
            </div>
            <div className="card-body">
              {TIMING_STEPS.map(step => (
                <TimingBar
                  key={step.key}
                  label={step.label}
                  icon={step.icon}
                  color={step.color}
                  ms={timing[step.key]}
                  maxMs={maxMs}
                />
              ))}
              {timingValues.length === 0 && (
                <p style={{ color: 'var(--text-secondary)', fontSize: 13, textAlign: 'center', margin: 0 }}>
                  Données de timing non disponibles
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
