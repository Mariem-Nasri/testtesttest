/**
 * api.js
 * ──────────────────────────────────────────────────────────────────────────────
 * Axios instance configured for the FastAPI backend.
 *
 * Base URL : VITE_API_BASE_URL env variable (default: http://localhost:8000/api)
 *
 * Interceptors:
 *  - Request  → inject JWT token from localStorage
 *  - Response → handle 401 (redirect to login)
 */

import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000, // 2 min (OCR can take time)
})

// ── Request interceptor — attach token ───────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('docai_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ── Response interceptor — handle 401 ────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired — clear storage and redirect
      localStorage.removeItem('docai_token')
      localStorage.removeItem('docai_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
