/**
 * Settings.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Pipeline configuration page.
 * Mirrors the PipelineConfig dataclass from full_pipeline/run_pipeline.py:
 *
 *   EMBEDDING_CONFIDENCE_THRESHOLD = 0.82   (skip Agent 2 if ≥ this)
 *   ROUTER_LLM_FALLBACK_THRESHOLD  = 0.45   (use LLM if < this)
 *   SCORE_THRESHOLD_HIGH           = 0.80
 *   SCORE_THRESHOLD_MEDIUM         = 0.60
 *   LLM_VALIDATION_THRESHOLD       = 0.85
 *   MAX_RETRIES                    = 3
 *   TIMEOUT_SECONDS                = 60
 *
 * Settings are saved to localStorage and sent to the backend on pipeline start.
 */

import { useState, useEffect } from 'react'
import toast                   from 'react-hot-toast'
import PageHeader              from '../components/common/PageHeader'

// ── Default values (match PipelineConfig) ────────────────────────────────────
const DEFAULTS = {
  backend:                       'groq',    // 'groq' | 'ollama'
  groq_api_key:                  '',
  ollama_model:                  'phi3.5:latest',
  embedding_confidence_threshold: 0.82,
  router_llm_fallback_threshold:  0.45,
  score_threshold_high:           0.80,
  score_threshold_medium:         0.60,
  llm_validation_threshold:       0.85,
  max_retries:                    3,
  timeout_seconds:                60,
}

const LS_KEY = 'docai_pipeline_config'

function loadConfig() {
  try {
    const saved = localStorage.getItem(LS_KEY)
    return saved ? { ...DEFAULTS, ...JSON.parse(saved) } : { ...DEFAULTS }
  } catch { return { ...DEFAULTS } }
}

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, icon, children }) {
  return (
    <div className="card mb-4">
      <div className="card-header d-flex align-items-center gap-2">
        <i className={`ti ${icon} text-primary-app`} />
        <span style={{ fontWeight: 600, fontSize: 15 }}>{title}</span>
      </div>
      <div className="card-body">{children}</div>
    </div>
  )
}

// ── Threshold slider row ──────────────────────────────────────────────────────
function ThresholdSlider({ label, description, name, value, min = 0, max = 1, step = 0.01, onChange }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)'

  return (
    <div className="mb-4">
      <div className="d-flex justify-content-between align-items-center mb-1">
        <div>
          <label className="form-label mb-0" style={{ fontWeight: 600, fontSize: 13.5 }}>{label}</label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{description}</div>
        </div>
        <span style={{
          minWidth: 52, textAlign: 'center',
          fontWeight: 700, fontSize: 15,
          color, fontFamily: 'Courier New, monospace',
        }}>
          {value.toFixed(2)}
        </span>
      </div>
      <input
        type="range"
        className="form-range"
        name={name}
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(name, parseFloat(e.target.value))}
        style={{ accentColor: 'var(--primary)' }}
      />
      <div className="d-flex justify-content-between" style={{ fontSize: 11, color: '#adb5bd' }}>
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────
export default function Settings() {
  const [cfg,     setCfg]     = useState(loadConfig)
  const [showKey, setShowKey] = useState(false)
  const [saved,   setSaved]   = useState(false)

  function set(key, value) { setCfg(prev => ({ ...prev, [key]: value })) }

  function handleSave() {
    localStorage.setItem(LS_KEY, JSON.stringify(cfg))
    setSaved(true)
    toast.success('Configuration sauvegardée')
    setTimeout(() => setSaved(false), 2000)
  }

  function handleReset() {
    setCfg({ ...DEFAULTS })
    localStorage.removeItem(LS_KEY)
    toast('Configuration réinitialisée aux valeurs par défaut')
  }

  return (
    <div>
      <PageHeader
        title="Paramètres du Pipeline"
        subtitle="Configuration des agents IA, seuils de confiance et backend LLM"
      />

      {/* ── 1. Backend LLM ── */}
      <Section title="Backend LLM" icon="ti-cpu">
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>
          Choisissez entre <strong>Groq API</strong> (cloud, rapide, gratuit) ou <strong>Ollama</strong> (local, 4 GB VRAM compatible).
        </p>

        {/* Backend toggle */}
        <div className="d-flex gap-3 mb-4">
          {[
            { value: 'groq',   label: 'Groq API',  icon: 'ti-cloud',      desc: 'Llama 4 Scout · 70B · 8B' },
            { value: 'ollama', label: 'Ollama',     icon: 'ti-server',     desc: 'Phi-3.5 (local WSL)' },
          ].map(opt => (
            <div
              key={opt.value}
              onClick={() => set('backend', opt.value)}
              style={{
                flex: 1, padding: '16px 20px', borderRadius: 12, cursor: 'pointer',
                border: `2px solid ${cfg.backend === opt.value ? 'var(--primary)' : 'var(--border-color)'}`,
                background: cfg.backend === opt.value ? 'rgba(0,167,111,0.1)' : 'rgba(255,255,255,0.03)',
                transition: 'all 0.2s',
              }}
            >
              <div className="d-flex align-items-center gap-2 mb-1">
                <i className={`ti ${opt.icon}`} style={{ fontSize: 20, color: cfg.backend === opt.value ? 'var(--primary)' : 'var(--text-secondary)' }} />
                <span style={{ fontWeight: 700, fontSize: 14, color: cfg.backend === opt.value ? 'var(--primary)' : 'var(--text-primary)' }}>{opt.label}</span>
                {cfg.backend === opt.value && <i className="ti ti-check ms-auto" style={{ color: 'var(--primary)' }} />}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{opt.desc}</div>
            </div>
          ))}
        </div>

        {/* Groq API Key */}
        {cfg.backend === 'groq' && (
          <div className="mb-3">
            <label className="form-label">
              Groq API Key
              <span className="badge bg-danger ms-2" style={{ fontSize: 10 }}>Requis</span>
            </label>
            <div style={{ position: 'relative' }}>
              <i className="ti ti-key" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#adb5bd', fontSize: 16 }} />
              <input
                type={showKey ? 'text' : 'password'}
                className="form-control"
                placeholder="gsk_..."
                value={cfg.groq_api_key}
                onChange={e => set('groq_api_key', e.target.value)}
                style={{ paddingLeft: 36, paddingRight: 44, fontFamily: 'Courier New, monospace', fontSize: 13 }}
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#adb5bd' }}
              >
                <i className={`ti ${showKey ? 'ti-eye-off' : 'ti-eye'}`} />
              </button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
              <i className="ti ti-info-circle me-1" />
              Obtenez votre clé gratuite sur console.groq.com. Stockée localement uniquement.
            </div>
          </div>
        )}

        {/* Ollama model */}
        {cfg.backend === 'ollama' && (
          <div>
            <label className="form-label">Modèle Ollama</label>
            <select
              className="form-select"
              value={cfg.ollama_model}
              onChange={e => set('ollama_model', e.target.value)}
              style={{ fontSize: 13, borderRadius: 8 }}
            >
              <option value="phi3.5:latest">phi3.5:latest (recommandé — 4 GB)</option>
              <option value="llama3.2:3b">llama3.2:3b</option>
              <option value="mistral:7b">mistral:7b</option>
            </select>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>
              <i className="ti ti-info-circle me-1" />
              Assurez-vous qu'Ollama tourne dans WSL : <code>ollama serve</code>
            </div>
          </div>
        )}
      </Section>

      {/* ── 2. Agent 1 — Router thresholds ── */}
      <Section title="Agent 1 — Router (Embedding)" icon="ti-route">
        <div className="alert alert-light border mb-4" style={{ fontSize: 12.5 }}>
          <i className="ti ti-info-circle me-1 text-primary-app" />
          Agent 1 utilise la similarité cosinus sur les embeddings. Si le score ≥ <strong>Embedding threshold</strong>, Agent 2 est ignoré (plus rapide).
          Si le score &lt; <strong>LLM fallback threshold</strong>, l'Agent 1 appelle le LLM en dernier recours.
        </div>

        <ThresholdSlider
          label="Embedding Confidence Threshold"
          description="Au-dessus → Agent 2 (Table) ignoré. Défaut : 0.82"
          name="embedding_confidence_threshold"
          value={cfg.embedding_confidence_threshold}
          onChange={set}
        />
        <ThresholdSlider
          label="Router LLM Fallback Threshold"
          description="En-dessous → Agent 1 appelle le LLM. Défaut : 0.45"
          name="router_llm_fallback_threshold"
          value={cfg.router_llm_fallback_threshold}
          onChange={set}
        />
      </Section>

      {/* ── 3. Agent 3 — Validator thresholds ── */}
      <Section title="Agent 3 — Validator" icon="ti-shield-check">
        <div className="alert alert-light border mb-4" style={{ fontSize: 12.5 }}>
          <i className="ti ti-info-circle me-1 text-primary-app" />
          Agent 3 classe chaque valeur selon son score de confiance et appelle le LLM si le score &lt; <strong>LLM Validation Threshold</strong>.
        </div>

        <ThresholdSlider
          label="Score Threshold — Haute confiance"
          description="Au-dessus → badge vert. Défaut : 0.80"
          name="score_threshold_high"
          value={cfg.score_threshold_high}
          onChange={set}
        />
        <ThresholdSlider
          label="Score Threshold — Confiance moyenne"
          description="Entre moyen et haut → badge orange. Défaut : 0.60"
          name="score_threshold_medium"
          value={cfg.score_threshold_medium}
          onChange={set}
        />
        <ThresholdSlider
          label="LLM Validation Threshold"
          description="En-dessous → Agent 3 appelle le LLM pour valider. Défaut : 0.85"
          name="llm_validation_threshold"
          value={cfg.llm_validation_threshold}
          onChange={set}
        />
      </Section>

      {/* ── 4. API & Retry ── */}
      <Section title="API & Fiabilité" icon="ti-refresh">
        <div className="row g-4">
          <div className="col-md-6">
            <label className="form-label">
              Nombre max de tentatives
              <span className="ms-2 text-muted" style={{ fontSize: 12 }}>MAX_RETRIES</span>
            </label>
            <div className="d-flex align-items-center gap-3">
              <input
                type="range" className="form-range" min={1} max={10} step={1}
                value={cfg.max_retries}
                onChange={e => set('max_retries', parseInt(e.target.value))}
                style={{ accentColor: 'var(--primary)' }}
              />
              <span style={{ fontWeight: 700, minWidth: 24, fontFamily: 'Courier New', color: 'var(--primary)' }}>
                {cfg.max_retries}
              </span>
            </div>
          </div>
          <div className="col-md-6">
            <label className="form-label">
              Timeout API (secondes)
              <span className="ms-2 text-muted" style={{ fontSize: 12 }}>TIMEOUT_SECONDS</span>
            </label>
            <div className="d-flex align-items-center gap-3">
              <input
                type="range" className="form-range" min={10} max={120} step={5}
                value={cfg.timeout_seconds}
                onChange={e => set('timeout_seconds', parseInt(e.target.value))}
                style={{ accentColor: 'var(--primary)' }}
              />
              <span style={{ fontWeight: 700, minWidth: 36, fontFamily: 'Courier New', color: 'var(--primary)' }}>
                {cfg.timeout_seconds}s
              </span>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Summary preview ── */}
      <div className="card mb-4 settings-terminal" style={{ position: 'relative', overflow: 'hidden' }}>
        <div className="card-header" style={{ borderBottom: '1px solid rgba(0,167,111,0.15)', color: '#a8b2c8', fontSize: 12, fontWeight: 600, letterSpacing: '0.5px' }}>
          <i className="ti ti-code me-1" />CONFIGURATION ACTIVE
        </div>
        <div className="card-body" style={{ fontFamily: 'Courier New, monospace', fontSize: 12, color: '#a8c0d6' }}>
          <div style={{ color: '#00c49f' }}># Backend</div>
          <div>backend = <span style={{ color: '#f5a623' }}>"{cfg.backend}"</span></div>
          {cfg.backend === 'groq' && <div>groq_api_key = <span style={{ color: '#f5a623' }}>"{cfg.groq_api_key ? '***' + cfg.groq_api_key.slice(-4) : 'NOT SET'}"</span></div>}
          {cfg.backend === 'ollama' && <div>ollama_model = <span style={{ color: '#f5a623' }}>"{cfg.ollama_model}"</span></div>}
          <div style={{ color: '#00c49f', marginTop: 8 }}># Thresholds</div>
          <div>EMBEDDING_CONFIDENCE_THRESHOLD = <span style={{ color: '#f5a623' }}>{cfg.embedding_confidence_threshold}</span></div>
          <div>ROUTER_LLM_FALLBACK_THRESHOLD  = <span style={{ color: '#f5a623' }}>{cfg.router_llm_fallback_threshold}</span></div>
          <div>SCORE_THRESHOLD_HIGH           = <span style={{ color: '#f5a623' }}>{cfg.score_threshold_high}</span></div>
          <div>SCORE_THRESHOLD_MEDIUM         = <span style={{ color: '#f5a623' }}>{cfg.score_threshold_medium}</span></div>
          <div>LLM_VALIDATION_THRESHOLD       = <span style={{ color: '#f5a623' }}>{cfg.llm_validation_threshold}</span></div>
          <div>MAX_RETRIES                    = <span style={{ color: '#f5a623' }}>{cfg.max_retries}</span></div>
          <div>TIMEOUT_SECONDS                = <span style={{ color: '#f5a623' }}>{cfg.timeout_seconds}</span></div>
        </div>
      </div>

      {/* ── Action buttons ── */}
      <div className="d-flex gap-3">
        <button className="btn btn-primary" onClick={handleSave}>
          <i className={`ti ${saved ? 'ti-check' : 'ti-device-floppy'} me-1`} />
          {saved ? 'Sauvegardé !' : 'Sauvegarder'}
        </button>
        <button className="btn btn-outline-secondary" onClick={handleReset}>
          <i className="ti ti-refresh me-1" />Réinitialiser par défaut
        </button>
      </div>
    </div>
  )
}
