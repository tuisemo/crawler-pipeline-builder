import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Spin } from 'antd'
import { setStoredSessionId } from '../services/apiClient'

export default function AuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('sessionId')
  const callbackError = searchParams.get('error')
  const callbackErrorMessage = searchParams.get('errorMessage')
  const nextPath = searchParams.get('nextPath') || '/'
  const hasStartedRef = useRef(false)
  const [error] = useState<string | null>(
    callbackErrorMessage || (callbackError ? `登录失败：${callbackError}` : null) || (!sessionId ? '登录回调参数异常，请重试' : null),
  )

  useEffect(() => {
    if (hasStartedRef.current || error) return
    hasStartedRef.current = true

    if (!sessionId) return
    setStoredSessionId(sessionId)

    // Clean up URL: replace to root without exposing sessionId in history
    window.history.replaceState(null, '', window.location.pathname + '#/')
    navigate(nextPath, { replace: true })
  }, [searchParams, navigate, nextPath, error, sessionId])

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
