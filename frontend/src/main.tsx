import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { AuthProvider } from './auth/AuthProvider'
import AuthCallbackPage from './auth/AuthCallbackPage'
import { RequireAuth } from './auth/RequireAuth'
import { ErrorBoundary } from './components/ErrorBoundary'
import { antdTheme } from './theme/antdTheme'
import './index.css'
import Layout from './app/Layout'
import HomePage from './app/HomePage'
import NotFoundPage from './app/NotFoundPage'
import TaskListPage from './app/TaskListPage'
import TaskDetailPage from './app/TaskDetailPage'
import WorkbenchPage from './app/WorkbenchPage'

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('Root element #root not found — check index.html.')
}

createRoot(rootEl).render(
  <StrictMode>
    <ErrorBoundary>
      <HashRouter>
        <AuthProvider>
          <ConfigProvider locale={zhCN} theme={antdTheme}>
            <AntdApp>
              <Routes>
                <Route path="/" element={<Layout />}>
                  <Route index element={<HomePage />} />
                  <Route path="auth/callback" element={<AuthCallbackPage />} />
                  <Route path="tasks" element={<RequireAuth><TaskListPage /></RequireAuth>} />
                  <Route path="tasks/:taskId" element={<RequireAuth><TaskDetailPage /></RequireAuth>} />
                  <Route path="tasks/:taskId/workbench" element={<RequireAuth><WorkbenchPage /></RequireAuth>} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Routes>
            </AntdApp>
          </ConfigProvider>
        </AuthProvider>
      </HashRouter>
    </ErrorBoundary>
  </StrictMode>,
)
