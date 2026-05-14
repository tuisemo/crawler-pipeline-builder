// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { HashRouter, Routes, Route } from 'react-router-dom'
import AuthCallbackPage from './AuthCallbackPage'
import { clearStoredSessionId } from '../services/apiClient'

function renderWithHashPath(hashPath: string) {
  // Set the hash before rendering
  window.location.hash = hashPath
  return render(
    <HashRouter>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/" element={<div data-testid="home">Home</div>} />
        <Route path="/tasks" element={<div data-testid="tasks">Tasks</div>} />
      </Routes>
    </HashRouter>,
  )
}

describe('AuthCallbackPage', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    clearStoredSessionId()
    window.location.hash = ''
  })

  it('stores sessionId and navigates to nextPath', async () => {
    renderWithHashPath('#/auth/callback?sessionId=test-session-123&nextPath=/tasks')

    await waitFor(() => {
      expect(window.sessionStorage.getItem('crawlerWorkflow.sessionId')).toBe('test-session-123')
    })
  })

  it('stores sessionId and defaults to / when nextPath is missing', async () => {
    renderWithHashPath('#/auth/callback?sessionId=test-session-456')

    await waitFor(() => {
      expect(window.sessionStorage.getItem('crawlerWorkflow.sessionId')).toBe('test-session-456')
    })
  })

  it('shows error when sessionId is missing', async () => {
    renderWithHashPath('#/auth/callback?nextPath=/tasks')

    await waitFor(() => {
      expect(screen.getByText('登录回调参数异常，请重试')).toBeTruthy()
    })
  })
})
