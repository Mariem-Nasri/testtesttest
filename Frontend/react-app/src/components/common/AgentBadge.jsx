/**
 * AgentBadge.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Shows which pipeline agent produced an extracted value.
 * Maps to the 4 agents in full_pipeline/agents/:
 *   agent1_router     → Router (embedding similarity)
 *   agent2_table      → Table Specialist
 *   agent3_validator  → Validator
 *   agent4_definition → Definition Reader
 *
 * Props:
 *   agent:     'agent1_router' | 'agent2_table' | 'agent3_validator' | 'agent4_definition'
 *   usedLlm:  bool  — true if Agent 1 fell back to LLM (router_used_llm)
 *   size:     'sm' | 'md'  (default 'md')
 */

const AGENT_CONFIG = {
  agent1_router: {
    label:   'Router',
    icon:    'ti-route',
    bg:      'rgba(46,134,171,0.12)',
    color:   '#1d6fa0',
    border:  'rgba(46,134,171,0.3)',
    tooltip: 'Agent 1 — Embedding Router (cosine similarity)',
  },
  agent2_table: {
    label:   'Table',
    icon:    'ti-table',
    bg:      'rgba(139,92,246,0.12)',
    color:   '#7c3aed',
    border:  'rgba(139,92,246,0.3)',
    tooltip: 'Agent 2 — Table Specialist',
  },
  agent3_validator: {
    label:   'Validator',
    icon:    'ti-shield-check',
    bg:      'rgba(245,166,35,0.12)',
    color:   '#b45309',
    border:  'rgba(245,166,35,0.3)',
    tooltip: 'Agent 3 — Validator (format + range checks)',
  },
  agent4_definition: {
    label:   'Definition',
    icon:    'ti-book',
    bg:      'rgba(0,167,111,0.12)',
    color:   '#007a52',
    border:  'rgba(0,167,111,0.3)',
    tooltip: 'Agent 4 — Definition Reader',
  },
}

const FALLBACK = {
  label: 'Unknown', icon: 'ti-cpu', bg: '#f3f4f6',
  color: '#6b7280', border: '#e5e7eb', tooltip: 'Agent inconnu',
}

export default function AgentBadge({ agent, usedLlm = false, size = 'md' }) {
  const cfg      = AGENT_CONFIG[agent] || FALLBACK
  const fontSize = size === 'sm' ? 11 : 12
  const iconSize = size === 'sm' ? 12 : 13
  const padding  = size === 'sm' ? '2px 7px' : '3px 9px'

  return (
    <span
      title={cfg.tooltip + (usedLlm ? ' + LLM fallback' : '')}
      style={{
        display:      'inline-flex',
        alignItems:   'center',
        gap:          5,
        padding,
        borderRadius: 20,
        fontSize,
        fontWeight:   600,
        background:   cfg.bg,
        color:        cfg.color,
        border:       `1px solid ${cfg.border}`,
        whiteSpace:   'nowrap',
        cursor:       'default',
      }}
    >
      <i className={`ti ${cfg.icon}`} style={{ fontSize: iconSize }} />
      {cfg.label}
      {/* LLM fallback indicator */}
      {usedLlm && (
        <span
          title="LLM fallback utilisé"
          style={{
            background: cfg.color,
            color: '#fff',
            borderRadius: 10,
            fontSize: 9,
            padding: '1px 5px',
            fontWeight: 700,
          }}
        >
          LLM
        </span>
      )}
    </span>
  )
}
