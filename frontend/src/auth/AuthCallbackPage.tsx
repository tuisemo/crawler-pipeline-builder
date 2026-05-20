import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Spin } from 'antd'
import { setStoredSessionId } from '../services/apiClient'

/**
 * AuthCallbackPage — handles the legacy BFF-redirect callback flow.
 *
 * In the current frontend-driven OAuth flow, the AuthProvider handles
 * code exchange on app startup (detecting ?code=xxx&state=yyy in the URL).
 * This page handles the older flow where the backend redirects to
 * /#/auth/callback?sessionId=xxx&nextPath=/tasks.
 */
export default function AuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('sessionId')
  const nextPath = searchParams.get('nextPath') || '/'
  const errorParam = searchParams.get('error')
  const errorMessage = searchParams.get('errorMessage')
  const hasStartedRef = useRef(false)

  useEffect(() => {
    if (hasStartedRef.current) return
    if (errorMessage || errorParam) {
      hasStartedRef.current = true
      return
    }
    if (!sessionId) return
    hasStartedRef.current = true

    setStoredSessionId(sessionId)
    window.history.replaceState(null, '', window.location.pathname + '#/')
    navigate(nextPath, { replace: true })
  }, [errorMessage, errorParam, navigate, nextPath, sessionId])

  const error = errorMessage || (errorParam ? `登录失败：${errorParam}` : (!sessionId ? '登录回调参数异常，请重试' : null))

  if (error) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '96px 24px' }}>
        <Alert type="error" title={error} showIcon style={{ maxWidth: 480, width: '100%' }} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '40vh' }}>
      <Spin size="large" description="正在完成登录…" />
    </div>
  )
}
