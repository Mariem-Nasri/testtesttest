/**
 * auth.js
 * ──────────────────────────────────────────────────────────────────────────────
 * Authentication API calls.
 * FastAPI typically uses OAuth2 password flow → POST /auth/token
 */

import api from './api'

/**
 * Login — POST /auth/token
 * Returns { access_token, token_type, user }
 */
export async function login(email, password) {
  // FastAPI OAuth2 expects form-data with username/password
  const formData = new URLSearchParams()
  formData.append('username', email)
  formData.append('password', password)

  const { data } = await api.post('/auth/token', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data
}

/**
 * Get current user — GET /auth/me
 */
export async function getMe() {
  const { data } = await api.get('/auth/me')
  return data
}
