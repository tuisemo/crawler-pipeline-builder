/**
 * RequireAuth — route guard component.
 *
 * Wraps protected routes (e.g. /tasks/**). If the user is not
 * authenticated the component stores the current path and
 * redirects to the login flow. After a successful login callback
 * the user is redirected back to the stored path.
 *
 * If the auth check is still loading, a loading indicator is
 * shown instead of flashing a login prompt.
 *
 * Homepage / is NOT wrapped — it remains publicly accessible.
 */

import { type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuth } from './useAuth'

interface RequireAuthProps {
  children: ReactNode
}

export function RequireAuth({ children }: RequireAuthProps) {
  const { isAuthenticated, isLoading, login } = useAuth()
  const location = useLocation()

  // 1. Auth check still in-flight → show loading indicator
  //    (no flash of login redirect)
  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '40vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  // 2. Not authenticated → store current path and redirect to login
  if (!isAuthenticated) {
    // Store the path the user was trying to reach so we can
    // redirect back after login.  The `login()` function calls
    // `window.location.href = /api/auth/login?next=<path>` which
    // triggers a full-page navigation — React rendering stops here.
    login(location.pathname + location.search)
    // Return null while the browser navigates away
    return null
  }

  // 3. Authenticated → render the protected content
  return <>{children}</>
}
