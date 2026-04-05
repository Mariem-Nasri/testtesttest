/**
 * ExtractFields.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Standalone page to define extraction fields and send them to backend.
 * 
 * Users can:
 *   - Add multiple extraction fields with: keyName, keyNameDescription, page, value, score
 *   - Export fields as JSON
 *   - Send all fields to backend in a single JSON array
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import PageHeader from '../components/common/PageHeader'
import FieldExtractor from '../components/upload/FieldExtractor'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export default function ExtractFields() {
  const navigate = useNavigate()
  const [fields, setFields] = useState([])
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit() {
    if (fields.length === 0) {
      toast.error('Ajoutez au moins un champ')
      return
    }

    if (!fields.every(f => f.keyName.trim())) {
      toast.error('Tous les champs doivent avoir un nom')
      return
    }

    setIsLoading(true)
    try {
      // Prepare data - remove internal 'id' field
      const payload = fields.map(({ keyName, keyNameDescription, page, value, score }) => ({
        keyName: keyName.trim(),
        keyNameDescription: keyNameDescription.trim(),
        page: page.trim(),
        value: value.trim(),
        score: score.trim(),
      }))

      // Get token from localStorage
      const token = localStorage.getItem('token')
      if (!token) {
        toast.error('Session expirée — reconnectez-vous')
        navigate('/login')
        return
      }

      // Send to backend
      const response = await fetch(`${API_BASE}/extraction-fields`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || `Erreur ${response.status}`)
      }

      const result = await response.json()
      
      // Success
      toast.success(`${fields.length} champ(s) envoyé(s) avec succès`)
      
      // Show result or redirect
      console.log('Response:', result)
      
      // Optional: reset fields or show results
      setFields([])
      
      // Optional: redirect to results or documents
      // navigate('/documents')

    } catch (err) {
      console.error('Submit error:', err)
      if (err.message.includes('Session expirée') || err.message.includes('401')) {
        toast.error('Session expirée — reconnectez-vous')
        navigate('/login')
      } else if (err.message.includes('localhost')) {
        toast.error('Impossible de contacter le serveur — assurez-vous que le backend est lancé', { duration: 5000 })
      } else {
        toast.error(err.message || 'Erreur lors de l\'envoi')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Définir les extractions"
        subtitle="Créez manuellement les champs à extraire et envoyez-les au backend"
      />

      <div className="row g-4">
        <div className="col-lg-8">
          <div className="card">
            <div className="card-body">
              <FieldExtractor
                fields={fields}
                onChange={setFields}
                onSubmit={handleSubmit}
                isLoading={isLoading}
              />
            </div>
          </div>
        </div>

        {/* Sidebar with info */}
        <div className="col-lg-4">
          {/* Info Card */}
          <div className="card mb-3">
            <div className="card-body">
              <h6 className="card-title mb-3 d-flex align-items-center gap-2">
                <i className="ti ti-info-circle text-info" />
                Guide d'utilisation
              </h6>
              <ul className="small list-unstyled" style={{ color: 'var(--text-secondary)' }}>
                <li className="mb-2">
                  <strong className="text-white">1. Ajouter un champ</strong><br/>
                  Cliquez sur "Ajouter un champ" pour créer une nouvelle entrée
                </li>
                <li className="mb-2">
                  <strong className="text-white">2. Remplir les informations</strong><br/>
                  Nom (obligatoire), description, page, valeur et score
                </li>
                <li className="mb-2">
                  <strong className="text-white">3. Envoyer les données</strong><br/>
                  Cliquez "Envoyer les champs" pour transmettre tout au backend
                </li>
                <li>
                  <strong className="text-white">4. Exporter en JSON</strong><br/>
                  Téléchargez les champs pour les réutiliser plus tard
                </li>
              </ul>
            </div>
          </div>

          {/* Format Card */}
          <div className="card mb-3">
            <div className="card-body">
              <h6 className="card-title mb-2">Format de sortie</h6>
              <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                <pre style={{ background: 'rgba(0,0,0,0.2)', padding: 12, borderRadius: 4, overflow: 'auto', maxHeight: 250 }}>
{`[
  {
    "keyName": "Loan Number",
    "keyNameDescription": "",
    "page": "1",
    "value": "",
    "score": "0.95"
  },
  {
    "keyName": "Agreement Date",
    "keyNameDescription": "",
    "page": "2",
    "value": "",
    "score": "0.87"
  }
]`}
                </pre>
              </code>
            </div>
          </div>

          {/* Stats Card */}
          {fields.length > 0 && (
            <div className="card border-success">
              <div className="card-body">
                <h6 className="card-title mb-2 text-success">Champs définis: {fields.length}</h6>
                <div className="small text-muted">
                  <div>✓ {fields.filter(f => f.keyName.trim()).length} avec nom</div>
                  <div>✓ {fields.filter(f => f.value.trim()).length} avec valeur</div>
                  <div>✓ {fields.filter(f => f.score.trim()).length} avec score</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
