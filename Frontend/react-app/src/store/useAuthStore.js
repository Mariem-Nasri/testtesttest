/**
 * useAuthStore.js
 * ──────────────────────────────────────────────────────────────────────────────
 * Zustand store for authentication state.
 * Persists token + user to localStorage so the session survives page refresh.
 */

import { create } from 'zustand'

const TOKEN_KEY = 'docai_token'
const USER_KEY  = 'docai_user'

const useAuthStore = create((set) => ({
  // Initial state — read from localStorage
  token: localStorage.getItem(TOKEN_KEY) || null,
  user:  JSON.parse(localStorage.getItem(USER_KEY) || 'null'),

  // Set auth after successful login
  setAuth: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    set({ token, user })
  },

  // Clear auth on logout
  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    set({ token: null, user: null })
  },
}))

export default useAuthStore
