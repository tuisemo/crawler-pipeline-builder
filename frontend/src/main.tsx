import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import './index.css'
import Layout from './app/Layout'
import HomePage from './app/HomePage'
import TaskListPage from './app/TaskListPage'
import TaskDetailPage from './app/TaskDetailPage'
import WorkbenchPage from './app/WorkbenchPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          fontFamily: "'Geist', Arial, -apple-system, system-ui, 'Segoe UI', Helvetica, sans-serif",
          fontSize: 14,
          colorPrimary: '#111111',
          colorLink: '#111111',
          colorInfo: '#111111',
          colorSuccess: '#10b981',
          colorWarning: '#f59e0b',
          colorError: '#ef4444',
          colorText: '#0f172a',
          colorTextSecondary: '#475569',
          colorTextTertiary: '#64748b',
          colorBgContainer: '#ffffff',
          colorBgLayout: '#f4f5f7',
          colorBgElevated: '#ffffff',
          colorBorder: 'rgba(148, 163, 184, 0.24)',
          colorBorderSecondary: 'rgba(148, 163, 184, 0.16)',
          colorFillSecondary: 'rgba(15, 23, 42, 0.04)',
          colorFillTertiary: 'rgba(15, 23, 42, 0.02)',
          borderRadius: 10,
          borderRadiusLG: 12,
          borderRadiusSM: 6,
          boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.14), 0 14px 28px rgba(15, 23, 42, 0.06)',
          boxShadowSecondary: '0 0 0 1px rgba(148, 163, 184, 0.16), 0 18px 42px rgba(15, 23, 42, 0.08)',
        },
        components: {
          Button: {
            borderRadius: 7,
            fontWeight: 500,
            controlHeight: 32,
            paddingInline: 14,
            defaultShadow: 'none',
            primaryShadow: '0 8px 18px rgba(15, 23, 42, 0.14)',
          },
          Card: {
            borderRadiusLG: 12,
            boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 12px 24px rgba(15, 23, 42, 0.05)',
          },
          Input: {
            borderRadius: 8,
            activeShadow: '0 0 0 3px rgba(15, 23, 42, 0.12)',
          },
          InputNumber: {
            borderRadius: 8,
            activeShadow: '0 0 0 3px rgba(15, 23, 42, 0.12)',
          },
          Select: {
            borderRadius: 8,
          },
          Tag: {
            borderRadiusSM: 9999,
          },
          Tabs: {
            fontWeightStrong: 600,
            inkBarColor: '#111111',
            itemSelectedColor: '#0f172a',
          },
          Collapse: {
            borderRadiusLG: 12,
          },
          Segmented: {
            borderRadius: 8,
            borderRadiusSM: 6,
          },
        },
      }}
    >
      <AntdApp>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route path="tasks" element={<TaskListPage />} />
              <Route path="tasks/:taskId" element={<TaskDetailPage />} />
              <Route path="tasks/:taskId/workbench" element={<WorkbenchPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </StrictMode>,
)
