/**
 * Login.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Spectacular dark-mode login page.
 * Split layout: animated branding panel (left) + glassmorphism form (right).
 * All animations are pure CSS — no extra dependencies.
 */

import { useState, useEffect } from 'react'
import { useNavigate }         from 'react-router-dom'
import toast                   from 'react-hot-toast'
import { login }               from '../../services/auth'
import useAuthStore            from '../../store/useAuthStore'
import PDFExtractVisual        from '../../components/visuals/PDFExtractVisual'


const FEATURES = [
  { icon: 'ti-robot',        label: 'Extraction automatique',  desc: 'Pipeline 4 agents IA sans intervention manuelle' },
  { icon: 'ti-shield-check', label: 'Validation intelligente', desc: 'Contrôle qualité et correction à chaque étape' },
  { icon: 'ti-chart-bar',    label: 'Résultats structurés',    desc: 'Export JSON précis prêt à l\'intégration' },
]

// ── Animated counter hook ─────────────────────────────────────────────────────
function useCounter(target, duration = 1200) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    let start = 0
    const step = target / (duration / 16)
    const timer = setInterval(() => {
      start += step
      if (start >= target) { setCount(target); clearInterval(timer) }
      else setCount(Math.floor(start))
    }, 16)
    return () => clearInterval(timer)
  }, [target, duration])
  return count
}

// ── Stat box (left panel) ──────────────────────────────────────────────────────
function StatBox({ value, label, suffix = '' }) {
  const count = useCounter(value)
  return (
    <div style={{
      textAlign: 'center',
      padding: '16px 20px',
      background: 'rgba(255,255,255,0.04)',
      border: '1px solid rgba(255,255,255,0.07)',
      borderRadius: 14,
      flex: 1,
    }}>
      <div style={{
        fontSize: 28, fontWeight: 800, color: '#00a76f',
        fontVariantNumeric: 'tabular-nums',
      }}>
        {count}{suffix}
      </div>
      <div style={{ fontSize: 11, color: 'rgba(148,163,184,0.7)', marginTop: 4, fontWeight: 500 }}>
        {label}
      </div>
    </div>
  )
}

// ── Main Login component ───────────────────────────────────────────────────────
export default function Login() {
  const navigate    = useNavigate()
  const { setAuth } = useAuthStore()

  const [form,     setForm]     = useState({ email: '', password: '' })
  const [loading,  setLoading]  = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [focused,  setFocused]  = useState(null)

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.email || !form.password) {
      toast.error('Veuillez remplir tous les champs')
      return
    }
    setLoading(true)
    try {
      const data = await login(form.email, form.password)
      setAuth(data.access_token, data.user)
      toast.success('Connexion réussie !')
      navigate('/dashboard')
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Email ou mot de passe incorrect'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  async function loginAsDemo() {
    setLoading(true)
    try {
      const data = await login('mariem@vermeg.com', 'vermeg2025')
      setAuth(data.access_token, data.user)
      toast.success('Bienvenue sur DocAI !')
      navigate('/dashboard')
    } catch {
      // Backend not running — set form fields so user can see credentials
      setForm({ email: 'mariem@vermeg.com', password: 'vermeg2025' })
      toast.error('Backend non disponible — lancez uvicorn main:app')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      {/* ── Ambient orbs ── */}
      <div className="login-orb login-orb-1" />
      <div className="login-orb login-orb-2" />
      <div className="login-orb login-orb-mid" />

      {/* ═══════════════════════════════════════════════════════════════
          LEFT — Branding Panel
          ═══════════════════════════════════════════════════════════════ */}
      <div className="login-left">
        {/* Brand */}
        <div className="login-brand">
          <div className="login-brand-icon">
            <i className="ti ti-brain" />
          </div>
          <span className="login-brand-name">DocAI</span>
        </div>

        {/* Hero text */}
        <div className="login-hero-title">
          Intelligence
          <span>Documentaire</span>
          Autonome
        </div>

        <p className="login-hero-subtitle">
          Plateforme d'extraction de champs dynamiques basée sur l'OCR
          et un pipeline de 4 agents IA. Conçue pour les documents
          financiers complexes chez VERMEG.
        </p>

        {/* PDF Extract Visual */}
        <PDFExtractVisual />

        {/* Stats row */}
        <div style={{ display: 'flex', gap: 12, marginTop: 36 }}>
          <StatBox value={4}   suffix=""  label="Agents IA" />
          <StatBox value={98}  suffix="%" label="Précision" />
          <StatBox value={120} suffix="+"  label="Docs/heure" />
        </div>

        {/* Feature highlights */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 24 }}>
          {FEATURES.map(f => (
            <div key={f.label} style={{
              display: 'flex', alignItems: 'center', gap: 14,
              padding: '10px 14px',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 10,
            }}>
              <div style={{
                width: 34, height: 34, borderRadius: 9, flexShrink: 0,
                background: 'rgba(0,167,111,0.15)',
                border: '1px solid rgba(0,167,111,0.22)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <i className={`ti ${f.icon}`} style={{ color: '#00a76f', fontSize: 17 }} />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.85)' }}>{f.label}</div>
                <div style={{ fontSize: 11, color: 'rgba(148,163,184,0.55)', marginTop: 2 }}>{f.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          RIGHT — Login Form
          ═══════════════════════════════════════════════════════════════ */}
      <div className="login-right">
        <div className="login-card">

          {/* Logo */}
          <div className="login-logo-area">
            <div className="login-logo-icon">
              <i className="ti ti-brain" />
            </div>
            <h1 className="login-title">Connexion</h1>
            <p className="login-subtitle">
              Accédez à votre espace DocAI
            </p>
          </div>

          {/* Form */}
          <form className="login-form" onSubmit={handleSubmit}>

            {/* Email */}
            <div className="mb-3">
              <label className="form-label">
                <i className="ti ti-mail me-1" style={{ fontSize: 12, opacity: 0.7 }} />
                Adresse email
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type="email"
                  name="email"
                  className="form-control"
                  placeholder="mariem@vermeg.com"
                  value={form.email}
                  onChange={handleChange}
                  onFocus={() => setFocused('email')}
                  onBlur={() => setFocused(null)}
                  autoComplete="email"
                  style={{
                    paddingLeft: 44,
                    transition: 'all 0.3s',
                    boxShadow: focused === 'email' ? '0 0 20px rgba(0,167,111,0.2)' : 'none',
                  }}
                />
                <i className="ti ti-mail" style={{
                  position: 'absolute', left: 14, top: '50%',
                  transform: 'translateY(-50%)',
                  color: focused === 'email' ? 'var(--primary)' : 'rgba(148,163,184,0.5)',
                  fontSize: 17, transition: 'color 0.2s',
                }} />
              </div>
            </div>

            {/* Password */}
            <div className="mb-4">
              <label className="form-label">
                <i className="ti ti-lock me-1" style={{ fontSize: 12, opacity: 0.7 }} />
                Mot de passe
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPass ? 'text' : 'password'}
                  name="password"
                  className="form-control"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={handleChange}
                  onFocus={() => setFocused('pass')}
                  onBlur={() => setFocused(null)}
                  autoComplete="current-password"
                  style={{
                    paddingLeft: 44, paddingRight: 46,
                    transition: 'all 0.3s',
                    boxShadow: focused === 'pass' ? '0 0 20px rgba(0,167,111,0.2)' : 'none',
                  }}
                />
                <i className="ti ti-lock" style={{
                  position: 'absolute', left: 14, top: '50%',
                  transform: 'translateY(-50%)',
                  color: focused === 'pass' ? 'var(--primary)' : 'rgba(148,163,184,0.5)',
                  fontSize: 17, transition: 'color 0.2s',
                }} />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  style={{
                    position: 'absolute', right: 12, top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'rgba(148,163,184,0.5)', fontSize: 17, padding: 0,
                    transition: 'color 0.2s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.color = 'var(--primary)'}
                  onMouseLeave={e => e.currentTarget.style.color = 'rgba(148,163,184,0.5)'}
                >
                  <i className={`ti ${showPass ? 'ti-eye-off' : 'ti-eye'}`} />
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              className="login-submit"
              disabled={loading}
            >
              {loading ? (
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <span className="spinner-border spinner-border-sm" style={{ width: 16, height: 16 }} />
                  Connexion en cours…
                </span>
              ) : (
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <i className="ti ti-login" />
                  Se connecter
                </span>
              )}
            </button>
          </form>

          {/* Divider */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0',
          }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.06)' }} />
            <span style={{ fontSize: 12, color: 'rgba(148,163,184,0.5)', fontWeight: 500 }}>ou</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.06)' }} />
          </div>

          {/* Demo login */}
          <button
            type="button"
            onClick={loginAsDemo}
            style={{
              width: '100%', padding: '13px',
              background: 'rgba(0,167,111,0.08)',
              border: '1px solid rgba(0,167,111,0.25)',
              borderRadius: 12,
              color: '#00a76f',
              fontSize: 14, fontWeight: 600, cursor: 'pointer',
              transition: 'all 0.25s',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = 'rgba(0,167,111,0.16)'
              e.currentTarget.style.boxShadow = '0 0 20px rgba(0,167,111,0.2)'
              e.currentTarget.style.transform = 'translateY(-1px)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'rgba(0,167,111,0.08)'
              e.currentTarget.style.boxShadow = 'none'
              e.currentTarget.style.transform = 'none'
            }}
          >
            <i className="ti ti-player-play" style={{ fontSize: 16 }} />
            Démo rapide — sans backend
          </button>

          {/* Footer */}
          <div style={{
            marginTop: 28, textAlign: 'center',
            fontSize: 11, color: 'rgba(148,163,184,0.4)',
            lineHeight: 1.6,
          }}>
            <div style={{ marginBottom: 6 }}>
              <span style={{
                display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                background: '#00c49f', marginRight: 6, verticalAlign: 'middle',
                boxShadow: '0 0 8px rgba(0,196,159,0.8)',
                animation: 'pulse-ring 2s infinite',
              }} />
              Système opérationnel
            </div>
            VERMEG — Projet de Fin d'Études 2025–2026
          </div>
        </div>
      </div>
    </div>
  )
}
