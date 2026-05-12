/**
 * useAuth hook — exposes auth state and actions.
 *
 * Usage:
 *   import { useAuth } from '../auth/useAuth'
 *
 * Must be used within an <AuthProvider>.
 */

import { useContext } from 'react'
import { AuthContext, type AuthState } from './AuthProvider'

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}

export type { AuthUser } from '../services/authApi'
