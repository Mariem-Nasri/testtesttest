/**
 * Results.jsx  — Enhanced
 * ──────────────────────────────────────────────────────────────────────────────
 * Full extraction results page.
 * Displays OCR text + extraction table with:
 *   - Agent badge (Router / Table / Validator / Definition)
 *   - Format badge (ratio, percentage, date, currency, number, text)
 *   - Confidence bar with colour coding
 *   - Debug panel (embedding_confidence, llm_calls, row/col labels)
 *   - Pipeline stats tab (confidence distribution + timing)
 *   - Filter by agent / confidence level / format
 */

import { useEffect, useState }  from 'react'
import { useParams, Link }      from 'react-router-dom'
import toast                    from 'react-hot-toast'
import ConfidenceBadge          from '../components/common/ConfidenceBadge'
import StatusBadge              from '../components/common/StatusBadge'
import AgentBadge               from '../components/common/AgentBadge'
import FormatBadge              from '../components/common/FormatBadge'
import PipelineStats            from '../components/results/PipelineStats'
import { getDocumentResults, getDocumentStatus, exportResults } from '../services/documents'
import usePolling               from '../hooks/usePolling'
import { formatDate }           from '../utils/formatters'

// ── Pipeline steps ────────────────────────────────────────────────────────────
const PIPELINE_STEPS = [
  { key: 'ocr',       label: 'OCR',        icon: 'ti-scan' },
  { key: 'indexing',  label: 'Indexation', icon: 'ti-database' },
  { key: 'agent1',    label: 'Router',     icon: 'ti-route' },
  { key: 'agent2',    label: 'Table',      icon: 'ti-table' },
  { key: 'agent3',    label: 'Validator',  icon: 'ti-shield-check' },
  { key: 'agent4',    label: 'Définitions',icon: 'ti-book' },
  { key: 'completed', label: 'Terminé',    icon: 'ti-check' },
]

// ── Mock data ─────────────────────────────────────────────────────────────────
const MOCK = {
  id: '00024', name: 'Test2.pdf', document_type: 'Accord de Prêt',
  status: 'completed', created_at: new Date(), avg_confidence: 0.88,
  pipeline_step: 'completed',
  ocr_text: `LOAN AGREEMENT

Between: THE REPUBLIC OF IRAQ (the "Borrower")
And: THE INTERNATIONAL BANK FOR RECONSTRUCTION AND DEVELOPMENT (the "Bank")

Loan Number: P-IQ-9240
Effective Date: March 15, 2024

Article II — THE LOAN
Section 2.01. The Bank agrees to lend EUR 500,000,000.
Section 2.02. Front-end Fee: 0.25% of the Loan amount.
Section 2.03. Interest rate: 6-month SOFR + fixed spread of 0.70%.`,
  pipeline_stats: {
    total_keys: 12,
    high_confidence: 7,
    medium_confidence: 3,
    low_confidence: 2,
    total_llm_calls: 5,
    keys_no_llm: 7,
    timing: { ocr: 4200, indexing: 380, agent1: 22, agent2: 1800, agent3: 95, agent4: 310 },
  },
  fields: [
    { keyName: 'Loan Number',      value: 'P-IQ-9240',            score: 0.92, page: '1', expected_format: 'text',       format_valid: true,  agent_used: 'agent1_router',     _debug: { embedding_confidence: 0.94, llm_calls: 0, router_used_llm: false, reason: 'High-confidence embedding match on page 1' } },
    { keyName: 'Agreement Date',   value: 'March 15, 2024',        score: 0.78, page: '1', expected_format: 'date',       format_valid: true,  agent_used: 'agent1_router',     _debug: { embedding_confidence: 0.61, llm_calls: 1, router_used_llm: true,  reason: 'LLM fallback used — low embedding score' } },
    { keyName: 'Borrower',         value: 'Republic of Iraq',      score: 0.95, page: '1', expected_format: 'text',       format_valid: true,  agent_used: 'agent1_router',     _debug: { embedding_confidence: 0.96, llm_calls: 0, router_used_llm: false, reason: 'Strong embedding match' } },
    { keyName: 'Lender / Bank',    value: 'IBRD',                  score: 0.91, page: '1', expected_format: 'text',       format_valid: true,  agent_used: 'agent4_definition', _debug: { embedding_confidence: 0.55, llm_calls: 0, router_used_llm: false, reason: 'Extracted from definition section' } },
    { keyName: 'Loan Amount',      value: 'EUR 500,000,000',       score: 0.89, page: '3', expected_format: 'currency',   format_valid: true,  agent_used: 'agent2_table',      _debug: { embedding_confidence: 0.79, llm_calls: 1, router_used_llm: false, row_label: 'Loan Amount', col_label: 'EUR', reason: 'Table extraction' } },
    { keyName: 'Loan Currency',    value: 'EUR',                   score: 0.97, page: '3', expected_format: 'text',       format_valid: true,  agent_used: 'agent1_router',     _debug: { embedding_confidence: 0.98, llm_calls: 0, router_used_llm: false, reason: 'Exact match' } },
    { keyName: 'Front-end Fee',    value: '0.25%',                 score: 0.84, page: '3', expected_format: 'percentage', format_valid: true,  agent_used: 'agent3_validator',  _debug: { embedding_confidence: 0.80, llm_calls: 1, router_used_llm: false, reason: 'Validated percentage format' } },
    { keyName: 'Interest Rate',    value: '6-month SOFR + 0.70%',  score: 0.71, page: '4', expected_format: 'percentage', format_valid: false, agent_used: 'agent1_router',     _debug: { embedding_confidence: 0.68, llm_calls: 1, router_used_llm: true,  reason: 'Mixed format — format validation failed' } },
    { keyName: 'Closing Date',     value: 'December 31, 2029',     score: 0.68, page: '5', expected_format: 'date',       format_valid: true,  agent_used: 'agent1_router',     _debug: { embedding_confidence: 0.65, llm_calls: 1, router_used_llm: true,  reason: 'Medium confidence — LLM confirmed' } },
    { keyName: 'Payment Dates',    value: 'April 15 and Oct 15',   score: 0.82, page: '5', expected_format: 'date',       format_valid: false, agent_used: 'agent3_validator',  _debug: { embedding_confidence: 0.77, llm_calls: 1, router_used_llm: false, reason: 'Multiple dates — format flagged' } },
    { keyName: 'Program Name',     value: 'Towards Digital Governance', score: 0.93, page: '1', expected_format: 'text', format_valid: true, agent_used: 'agent4_definition',  _debug: { embedding_confidence: 0.91, llm_calls: 0, router_used_llm: false, reason: 'Found in definitions section' } },
    { keyName: 'Commitment Charge',value: '0.25% per annum',       score: 0.44, page: '4', expected_format: 'percentage', format_valid: false, agent_used: 'agent2_table',     _debug: { embedding_confidence: 0.40, llm_calls: 2, router_used_llm: true,  row_label: 'Charge', col_label: 'Annual', reason: 'Low confidence — ambiguous table cell' } },
  ],
}

// ── Filter options ────────────────────────────────────────────────────────────
const AGENT_FILTERS  = [
  { value: '',                 label: 'Tous les agents' },
  { value: 'agent1_router',    label: 'Router' },
  { value: 'agent2_table',     label: 'Table' },
  { value: 'agent3_validator', label: 'Validator' },
  { value: 'agent4_definition',label: 'Definition' },
]

const CONFIDENCE_FILTERS = [
  { value: '',       label: 'Toutes confiances' },
  { value: 'high',   label: '≥ 80% (haute)' },
  { value: 'medium', label: '50–79% (moyenne)' },
  { value: 'low',    label: '< 50% (faible)' },
]

const FORMAT_FILTERS = [
  { value: '',           label: 'Tous formats' },
  { value: 'text',       label: 'Texte' },
  { value: 'date',       label: 'Date' },
  { value: 'currency',   label: 'Montant' },
  { value: 'percentage', label: 'Pourcentage' },
  { value: 'ratio',      label: 'Ratio' },
  { value: 'number',     label: 'Nombre' },
]

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Results() {
  const { id } = useParams()

  const [data,       setData]       = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [activeTab,  setActiveTab]  = useState('results')   // 'results' | 'stats' | 'ocr'
  const [search,     setSearch]     = useState('')
  const [agentFilter,      setAgentFilter]      = useState('')
  const [confidenceFilter, setConfidenceFilter] = useState('')
  const [formatFilter,     setFormatFilter]     = useState('')
  const [expandedRow,      setExpandedRow]      = useState(null)  // debug panel
  const [exporting,        setExporting]        = useState(false)

  // ── Fetch ────────────────────────────────────────────────────────────────
  async function fetchData() {
    try {
      const res = await getDocumentResults(id)
      setData(res)
      return res
    } catch {
      setData(MOCK)
      return MOCK
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [id])

  // ── Polling while pipeline running ───────────────────────────────────────
  usePolling(async () => {
    if (data?.status === 'completed' || data?.status === 'error') return
    const fresh = await fetchData()
    if (fresh?.status === 'completed') toast.success('Extraction terminée !')
  }, data?.status !== 'completed' && data?.status !== 'error' ? 3000 : null)

  // ── Export ────────────────────────────────────────────────────────────────
  async function handleExport(format) {
    setExporting(true)
    try {
      const blob = await exportResults(id, format)
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url
      a.download = `${data?.name?.replace('.pdf','') || 'results'}.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      const content = format === 'json'
        ? JSON.stringify(data?.fields || [], null, 2)
        : ['keyName,value,score,page,agent,format'].concat(
            (data?.fields || []).map(f => `"${f.keyName}","${f.value ?? ''}",${f.score ?? ''},${f.page ?? ''},${f.agent_used ?? ''},${f.expected_format ?? ''}`)
          ).join('\n')
      const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a'); a.href = url; a.download = `extraction.${format}`; a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  if (loading) return (
    <div className="text-center py-5">
      <div className="spinner-border text-primary" />
      <p className="mt-2 text-muted small">Chargement des résultats...</p>
    </div>
  )

  // ── Apply filters ─────────────────────────────────────────────────────────
  const filtered = (data?.fields || []).filter(f => {
    const pct = f.score > 1 ? f.score : (f.score ?? 0) * 100
    if (search && !f.keyName.toLowerCase().includes(search.toLowerCase()) &&
        !String(f.value ?? '').toLowerCase().includes(search.toLowerCase())) return false
    if (agentFilter      && f.agent_used        !== agentFilter) return false
    if (formatFilter     && f.expected_format   !== formatFilter) return false
    if (confidenceFilter === 'high'   && pct < 80)  return false
    if (confidenceFilter === 'medium' && (pct < 50 || pct >= 80)) return false
    if (confidenceFilter === 'low'    && pct >= 50) return false
    return true
  })

  const stepIdx = PIPELINE_STEPS.findIndex(s => s.key === (data?.pipeline_step || 'completed'))

  return (
    <div>
      {/* ── Header ── */}
      <div className="d-flex align-items-start justify-content-between mb-4 flex-wrap gap-3">
        <div>
          <div className="d-flex align-items-center gap-2 mb-1">
            <Link to="/documents" className="btn btn-sm p-1" style={{ color: 'var(--text-secondary)', background: 'none', border: 'none' }}>
              <i className="ti ti-arrow-left" style={{ fontSize: 18 }} />
            </Link>
            <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
              {data?.name}
              <span className="doc-id-cell ms-2" style={{ fontSize: 13 }}>#{id}</span>
            </h2>
          </div>
          <div className="d-flex align-items-center gap-2 flex-wrap">
            <span style={{ display:'inline-block', padding:'3px 10px', background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.1)', borderRadius:6, fontSize:12, fontWeight:500, color:'var(--text-secondary)' }}>{data?.document_type}</span>
            <StatusBadge status={data?.status} />
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{formatDate(data?.created_at)}</span>
            {data?.avg_confidence != null && (
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Score moyen&nbsp;
                <strong style={{ color: data.avg_confidence >= 0.8 ? 'var(--success)' : 'var(--warning)' }}>
                  {Math.round(data.avg_confidence * 100)}%
                </strong>
              </span>
            )}
          </div>
        </div>

        {/* Export */}
        <div className="d-flex gap-2 flex-wrap">
          <button className="btn btn-outline-primary btn-sm" onClick={() => handleExport('json')} disabled={exporting || data?.status !== 'completed'}>
            <i className="ti ti-file-type-json me-1" />JSON
          </button>
          <button className="btn btn-outline-secondary btn-sm" onClick={() => handleExport('csv')} disabled={exporting || data?.status !== 'completed'}>
            <i className="ti ti-file-type-csv me-1" />CSV
          </button>
        </div>
      </div>

      {/* ── Pipeline Stepper ── */}
      <div className="card mb-4">
        <div className="card-body py-3 px-4">
          <div className="pipeline-stepper">
            {PIPELINE_STEPS.map((step, idx) => {
              const isDone   = data?.status === 'completed' || idx < stepIdx
              const isActive = idx === stepIdx && data?.status !== 'completed'
              const isError  = data?.status === 'error' && idx === stepIdx
              return (
                <div key={step.key} className={`step-item ${isDone ? 'completed' : ''} ${isActive ? 'active' : ''}`}>
                  <div className={`step-circle ${isError ? 'error' : isDone ? 'completed' : isActive ? 'active' : ''}`}>
                    {isError  ? <i className="ti ti-x" style={{ fontSize: 13 }} /> :
                     isDone   ? <i className="ti ti-check" style={{ fontSize: 13 }} /> :
                     isActive ? <span className="spinner-border spinner-border-sm" style={{ width: 14, height: 14 }} /> :
                     <i className={`ti ${step.icon}`} style={{ fontSize: 13 }} />}
                  </div>
                  <span className="step-label">{step.label}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── Error alert ── */}
      {data?.status === 'error' && (
        <div className="alert alert-danger d-flex gap-2 mb-4">
          <i className="ti ti-alert-circle mt-1" />
          <div>
            <strong>Erreur lors du traitement</strong>
            <div style={{ fontSize: 13 }}>{data?.error_message || 'Veuillez relancer l\'extraction.'}</div>
          </div>
        </div>
      )}

      {/* ── Tabs ── */}
      <ul className="nav nav-tabs mb-4" style={{ borderBottom: '2px solid var(--border-color)' }}>
        {[
          { key: 'results', label: 'Résultats d\'extraction', icon: 'ti-table-export' },
          { key: 'json',    label: 'JSON brut',               icon: 'ti-braces' },
          { key: 'stats',   label: 'Statistiques pipeline',   icon: 'ti-chart-bar' },
          { key: 'ocr',     label: 'Texte OCR brut',          icon: 'ti-scan' },
        ].map(tab => (
          <li key={tab.key} className="nav-item">
            <button
              className={`nav-link ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
              style={{
                border: 'none',
                borderBottom: activeTab === tab.key ? '2px solid var(--primary)' : '2px solid transparent',
                color: activeTab === tab.key ? 'var(--primary)' : 'var(--text-secondary)',
                fontWeight: activeTab === tab.key ? 600 : 400,
                background: 'none',
                padding: '10px 18px',
                marginBottom: -2,
                fontSize: 13.5,
              }}
            >
              <i className={`ti ${tab.icon} me-1`} />{tab.label}
              {tab.key === 'results' && (
                <span className="ms-2 badge bg-primary" style={{ fontSize: 11 }}>
                  {filtered.length}/{data?.fields?.length ?? 0}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>

      {/* ══ TAB: Results ══ */}
      {activeTab === 'results' && (
        <div>
          {/* Filters bar */}
          <div className="card mb-3">
            <div className="card-body py-3">
              <div className="row g-2 align-items-center">
                <div className="col-md-4">
                  <div className="search-bar-wrap">
                    <i className="ti ti-search" />
                    <input type="text" className="form-control" placeholder="Rechercher un champ..." value={search} onChange={e => setSearch(e.target.value)} />
                  </div>
                </div>
                <div className="col-md-2">
                  <select className="form-select" style={{ fontSize: 13, height: 38, borderRadius: 8 }} value={agentFilter} onChange={e => setAgentFilter(e.target.value)}>
                    {AGENT_FILTERS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div className="col-md-2">
                  <select className="form-select" style={{ fontSize: 13, height: 38, borderRadius: 8 }} value={confidenceFilter} onChange={e => setConfidenceFilter(e.target.value)}>
                    {CONFIDENCE_FILTERS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div className="col-md-2">
                  <select className="form-select" style={{ fontSize: 13, height: 38, borderRadius: 8 }} value={formatFilter} onChange={e => setFormatFilter(e.target.value)}>
                    {FORMAT_FILTERS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div className="col-md-2">
                  {(search || agentFilter || confidenceFilter || formatFilter) && (
                    <button className="btn btn-outline-secondary btn-sm w-100" onClick={() => { setSearch(''); setAgentFilter(''); setConfidenceFilter(''); setFormatFilter('') }}>
                      <i className="ti ti-x me-1" />Réinitialiser
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Results table */}
          <div className="card">
            <div className="card-body p-0">
              {data?.status !== 'completed' && data?.status !== 'error' ? (
                <div className="text-center py-5">
                  <div className="spinner-border text-primary" />
                  <p className="mt-2 text-muted small">Pipeline en cours...</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="table mb-0">
                    <thead>
                      <tr>
                        <th style={{ width: 28 }} />
                        <th>Champ</th>
                        <th>Valeur extraite</th>
                        <th>Format</th>
                        <th>Page</th>
                        <th style={{ minWidth: 140 }}>Confiance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((field, idx) => (
                        <>
                          <tr
                            key={idx}
                            style={{ cursor: 'pointer' }}
                            onClick={() => setExpandedRow(expandedRow === idx ? null : idx)}
                          >
                            {/* Expand toggle */}
                            <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                              <i className={`ti ${expandedRow === idx ? 'ti-chevron-down' : 'ti-chevron-right'}`} />
                            </td>

                            {/* Key name */}
                            <td>
                              <span className="fw-600" style={{ fontSize: 13 }}>{field.keyName}</span>
                              {field._debug?.router_used_llm && (
                                <span title="LLM fallback utilisé par Agent 1" style={{ marginLeft: 6, fontSize: 10, background: 'rgba(124,58,237,0.1)', color: '#7c3aed', borderRadius: 4, padding: '1px 5px', fontWeight: 600 }}>
                                  LLM
                                </span>
                              )}
                            </td>

                            {/* Value */}
                            <td className="result-value-cell">
                              {field.value ?? <span style={{ color: '#adb5bd', fontStyle: 'italic' }}>Non trouvé</span>}
                            </td>

                            {/* Format */}
                            <td>
                              <FormatBadge format={field.expected_format} formatValid={field.format_valid} />
                            </td>

                            {/* Page */}
                            <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{field.page || '—'}</td>

                            {/* Confidence */}
                            <td><ConfidenceBadge score={field.score ?? 0} /></td>
                          </tr>

                          {/* ── Debug panel (expanded row) ── */}
                          {expandedRow === idx && (
                            <tr key={`debug-${idx}`} style={{ background: 'rgba(0,167,111,0.03)' }}>
                              <td colSpan={6} style={{ padding: '12px 20px 16px 48px' }}>
                                <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', fontSize: 12.5 }}>
                                  <DebugItem label="Embedding confidence" value={(field.embedding_confidence ?? field._debug?.embedding_confidence) != null ? `${((field.embedding_confidence ?? field._debug?.embedding_confidence) * 100).toFixed(1)}%` : '—'} icon="ti-cpu" />
                                  <DebugItem label="Appels LLM" value={field.llm_calls ?? field._debug?.llm_calls ?? 0} icon="ti-brain" />
                                  <DebugItem label="Row label" value={field.row_label || field._debug?.row_label || '—'} icon="ti-row-insert-bottom" />
                                  <DebugItem label="Col label" value={field.col_label || field._debug?.col_label || '—'} icon="ti-column-insert-right" />
                                  <DebugItem label="Format valide" value={field.format_valid ? 'Oui ✓' : 'Non ✗'} icon="ti-check" color={field.format_valid ? '#16a34a' : '#dc2626'} />
                                  {field._debug?.reason && (
                                    <div style={{ flex: '1 1 100%', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                                      <i className="ti ti-info-circle me-1" />
                                      {field._debug.reason}
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      ))}
                      {filtered.length === 0 && (
                        <tr>
                          <td colSpan={6} className="text-center py-4" style={{ color: 'var(--text-secondary)' }}>
                            Aucun champ ne correspond aux filtres
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ══ TAB: JSON ══ */}
      {activeTab === 'json' && (
        <div className="card">
          <div className="card-header d-flex align-items-center gap-2" style={{ fontSize: 13 }}>
            <i className="ti ti-braces text-primary-app" />
            Résultats JSON bruts
            <button
              className="btn btn-outline-secondary btn-sm ms-auto"
              style={{ fontSize: 12 }}
              onClick={() => {
                const blob = new Blob(
                  [JSON.stringify(data?.fields ?? [], null, 2)],
                  { type: 'application/json' }
                )
                const url = URL.createObjectURL(blob)
                const a   = document.createElement('a')
                a.href    = url
                a.download = `${data?.name?.replace('.pdf','') ?? 'results'}_extraction.json`
                a.click()
                URL.revokeObjectURL(url)
              }}
            >
              <i className="ti ti-download me-1" />Télécharger
            </button>
          </div>
          <div className="card-body p-0">
            <pre style={{
              margin: 0,
              padding: '20px 24px',
              background: 'transparent',
              color: '#7dd3fc',
              fontSize: 12.5,
              fontFamily: 'Courier New, monospace',
              overflowX: 'auto',
              maxHeight: 600,
              overflowY: 'auto',
            }}>
              {JSON.stringify(data?.fields ?? [], null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* ══ TAB: Stats ══ */}
      {activeTab === 'stats' && (
        <PipelineStats stats={data?.pipeline_stats} />
      )}

      {/* ══ TAB: OCR ══ */}
      {activeTab === 'ocr' && (
        <div className="card">
          <div className="card-header d-flex align-items-center gap-2">
            <i className="ti ti-scan text-primary-app" />
            Texte OCR extrait (DeepDoctection + DocTr)
            <span style={{ display:'inline-block', padding:'3px 10px', background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.08)', borderRadius:6, fontSize:11, color:'var(--text-secondary)', marginLeft:'auto' }}>Lecture seule</span>
          </div>
          <div className="card-body">
            {data?.ocr_text
              ? <div className="ocr-viewer">{data.ocr_text}</div>
              : <div className="empty-state py-4"><i className="ti ti-scan" style={{ fontSize: 40 }} /><p>Texte OCR non disponible</p></div>
            }
          </div>
        </div>
      )}
    </div>
  )
}

// ── Debug item (helper) ───────────────────────────────────────────────────────
function DebugItem({ label, value, icon, color }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
        <i className={`ti ${icon} me-1`} />{label}
      </div>
      <div style={{ fontWeight: 600, color: color || 'var(--text-primary)', fontFamily: 'Courier New, monospace' }}>
        {value}
      </div>
    </div>
  )
}
