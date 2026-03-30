/**
 * Dashboard.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Main dashboard page.
 * Adapted from Dasher template's index.html welcome + stats cards layout.
 *
 * Sections:
 *  1. Welcome banner
 *  2. KPI cards (4 metrics)
 *  3. Donut chart (documents by type)  +  Recent activity feed
 *  4. Recent documents table (last 5)
 */

import { useEffect, useState } from 'react'
import { Link }                from 'react-router-dom'
import ReactApexChart          from 'react-apexcharts'
import StatusBadge             from '../components/common/StatusBadge'
import ConfidenceBadge         from '../components/common/ConfidenceBadge'
import { getStats, getDocuments } from '../services/documents'
import { formatDate }          from '../utils/formatters'
import useAuthStore            from '../store/useAuthStore'
import PipelineFlowVisual     from '../components/visuals/PipelineFlowVisual'

// ── KPI Card component (local to this page) ───────────────────────────────────
function KPICard({ icon, label, value, variant = 'primary' }) {
  return (
    <div className={`kpi-card ${variant}`}>
      <div className={`kpi-icon ${variant}`}>
        <i className={`ti ${icon}`} />
      </div>
      <div className="kpi-value">{value ?? '—'}</div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}

// ── Donut chart options ───────────────────────────────────────────────────────
function buildChartOptions(labels) {
  return {
    chart:   { type: 'donut', fontFamily: 'Inter, sans-serif', background: 'transparent' },
    labels,
    colors:  ['#00a76f', '#58a6ff', '#f5a623', '#94a3b8'],
    legend:  {
      position: 'bottom', fontSize: '13px',
      labels: { colors: '#94a3b8' },
    },
    plotOptions: {
      pie: {
        donut: {
          size: '68%',
          labels: {
            show: true,
            total: {
              show: true,
              label: 'Total',
              fontSize: '14px',
              fontWeight: 600,
              color: '#e2e8f0',
            },
            value: { color: '#e2e8f0', fontSize: '22px', fontWeight: 700 },
          },
        },
      },
    },
    dataLabels: { enabled: false },
    stroke: { width: 0 },
    tooltip: {
      theme: 'dark',
      style: { fontSize: '13px' },
    },
  }
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { user }  = useAuthStore()
  const [stats,   setStats]   = useState(null)
  const [docs,    setDocs]    = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [statsData, docsData] = await Promise.all([
          getStats(),
          getDocuments({ limit: 5 }),
        ])
        setStats(statsData)
        setDocs(docsData.documents || docsData)
      } catch (err) {
        console.error('Dashboard load error:', err)
        // Use mock data so the UI still renders during development
        setStats(MOCK_STATS)
        setDocs(MOCK_DOCS)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return <DashboardSkeleton />

  const typeLabels  = stats?.by_type ? Object.keys(stats.by_type)   : ['Accord de Prêt', 'Rapport', 'Contrat', 'Autre']
  const typeSeries  = stats?.by_type ? Object.values(stats.by_type) : [12, 6, 4, 2]

  return (
    <div>
      {/* ── 1. Welcome banner ── */}
      <div className="welcome-banner mb-4">
        <div className="row align-items-center">
          <div className="col-md-8">
            <h2>👋 Bonjour, {user?.name || 'Mariem'}</h2>
            <p>
              Bienvenue sur DocAI Platform. Analysez vos documents contractuels
              grâce à l'OCR et aux agents IA spécialisés.
            </p>
            <Link to="/upload" className="btn btn-light btn-sm fw-600">
              <i className="ti ti-cloud-upload me-1" /> Nouveau document
            </Link>
          </div>
          <div className="col-md-4 d-none d-md-block">
            <PipelineFlowVisual />
          </div>
        </div>
      </div>

      {/* ── 2. KPI Cards ── */}
      <div className="row g-4 mb-4">
        <div className="col-6 col-xl-3">
          <KPICard
            icon="ti-files"
            label="Documents traités"
            value={stats?.total_documents ?? 0}
            variant="primary"
          />
        </div>
        <div className="col-6 col-xl-3">
          <KPICard
            icon="ti-chart-bar"
            label="Taux de succès"
            value={`${stats?.success_rate ?? 0}%`}
            variant="success"
          />
        </div>
        <div className="col-6 col-xl-3">
          <KPICard
            icon="ti-clock"
            label="Tps moyen (sec)"
            value={stats?.avg_processing_time ?? '—'}
            variant="warning"
          />
        </div>
        <div className="col-6 col-xl-3">
          <KPICard
            icon="ti-loader-2"
            label="En cours"
            value={stats?.processing_count ?? 0}
            variant="info"
          />
        </div>
      </div>

      {/* ── 3. Chart + Activity ── */}
      <div className="row g-4 mb-4">
        {/* Donut chart */}
        <div className="col-lg-5">
          <div className="card h-100">
            <div className="card-header d-flex align-items-center gap-2">
              <i className="ti ti-chart-donut text-primary-app" />
              Répartition par type
            </div>
            <div className="card-body d-flex justify-content-center align-items-center">
              <ReactApexChart
                type="donut"
                series={typeSeries}
                options={buildChartOptions(typeLabels)}
                height={280}
                width="100%"
              />
            </div>
          </div>
        </div>

        {/* Recent activity */}
        <div className="col-lg-7">
          <div className="card h-100">
            <div className="card-header d-flex align-items-center gap-2">
              <i className="ti ti-activity text-primary-app" />
              Activité récente
            </div>
            <div className="card-body p-0">
              {docs.slice(0, 5).map((doc) => (
                <div
                  key={doc.id}
                  className="d-flex align-items-center justify-content-between px-4 py-3"
                  style={{ borderBottom: '1px solid var(--border-color)' }}
                >
                  <div className="d-flex align-items-center gap-3">
                    <div
                      style={{
                        width: 36, height: 36,
                        background: 'var(--primary-light)',
                        borderRadius: 8,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      <i className="ti ti-file-text" style={{ color: 'var(--primary)' }} />
                    </div>
                    <div>
                      <div className="fw-600" style={{ fontSize: 13 }}>{doc.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                        {formatDate(doc.created_at)}
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={doc.status} />
                </div>
              ))}

              {docs.length === 0 && (
                <div className="empty-state">
                  <i className="ti ti-inbox" />
                  <h5>Aucun document</h5>
                  <p>Uploadez votre premier document pour commencer</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── 4. Recent documents table ── */}
      <div className="card">
        <div className="card-header d-flex align-items-center justify-content-between">
          <span className="d-flex align-items-center gap-2">
            <i className="ti ti-table text-primary-app" />
            Documents récents
          </span>
          <Link to="/documents" className="btn btn-outline-primary btn-sm">
            Voir tout
          </Link>
        </div>
        <div className="card-body p-0">
          <div className="table-responsive">
            <table className="table mb-0">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Nom du document</th>
                  <th>Type</th>
                  <th>Date</th>
                  <th>Statut</th>
                  <th>Confiance</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id}>
                    <td className="doc-id-cell">#{doc.id}</td>
                    <td className="doc-name-cell">{doc.name}</td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '3px 10px',
                        background: 'rgba(255,255,255,0.06)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 6, fontSize: 12, fontWeight: 500,
                        color: 'var(--text-secondary)',
                      }}>
                        {doc.document_type || 'Non défini'}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                      {formatDate(doc.created_at)}
                    </td>
                    <td><StatusBadge status={doc.status} /></td>
                    <td>
                      {doc.avg_confidence != null
                        ? <ConfidenceBadge score={doc.avg_confidence} />
                        : <span style={{ color: '#adb5bd', fontSize: 12 }}>—</span>
                      }
                    </td>
                    <td>
                      {doc.status === 'completed' && (
                        <Link
                          to={`/documents/${doc.id}/results`}
                          className="btn btn-sm btn-outline-primary"
                        >
                          <i className="ti ti-eye me-1" />Voir
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
                {docs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center py-5" style={{ color: 'var(--text-secondary)' }}>
                      Aucun document traité pour l'instant
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Loading skeleton ──────────────────────────────────────────────────────────
function DashboardSkeleton() {
  return (
    <div>
      <div className="welcome-banner mb-4" style={{ opacity: 0.5 }}>
        <div style={{ height: 80 }} />
      </div>
      <div className="row g-4 mb-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="col-6 col-xl-3">
            <div className="card" style={{ height: 120 }}>
              <div className="card-body">
                <div className="skeleton" style={{ height: 16, width: '60%', borderRadius: 4, marginBottom: 12 }} />
                <div className="skeleton" style={{ height: 28, width: '40%', borderRadius: 4 }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Mock data (used when backend is not yet connected) ────────────────────────
const MOCK_STATS = {
  total_documents:     24,
  success_rate:        87,
  avg_processing_time: 42,
  processing_count:    3,
  by_type: {
    'Accord de Prêt': 13,
    'Rapport Financier': 7,
    'Contrat': 3,
    'Autre': 1,
  },
}

const MOCK_DOCS = [
  { id: '00024', name: 'Test2.pdf',         document_type: 'Accord de Prêt',    status: 'completed',  avg_confidence: 0.91, created_at: new Date() },
  { id: '00023', name: 'Report_2024.pdf',   document_type: 'Rapport Financier', status: 'processing', avg_confidence: null, created_at: new Date() },
  { id: '00022', name: 'Contract_A.pdf',    document_type: 'Contrat',           status: 'error',      avg_confidence: null, created_at: new Date() },
  { id: '00021', name: 'Loan_IQ_9240.pdf',  document_type: 'Accord de Prêt',    status: 'completed',  avg_confidence: 0.74, created_at: new Date() },
]
