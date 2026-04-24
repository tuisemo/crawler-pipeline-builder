import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntdApp, ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: 'var(--sd-color-primary)',
          colorSuccess: 'var(--sd-color-success)',
          colorWarning: '#d97706',
          colorError: '#dc2626',
          colorInfo: 'var(--sd-color-primary)',
          borderRadius: 10,
          borderRadiusSM: 8,
          borderRadiusLG: 14,
          fontFamily: 'var(--sd-font-ui)',
          controlHeight: 32,
          controlHeightSM: 28,
          controlHeightLG: 36,
          lineHeight: 1.55,
          colorBgContainer: 'var(--sd-color-surface)',
          colorBgLayout: 'var(--sd-color-bg-base)',
          colorBorder: 'var(--sd-color-border-soft)',
          colorText: 'var(--sd-color-text)',
          colorTextSecondary: 'var(--sd-color-text-secondary)',
          colorTextDescription: 'var(--sd-color-text-secondary)',
          colorTextPlaceholder: 'var(--sd-color-text-secondary)',
          boxShadow: '0 10px 24px rgba(15, 23, 42, 0.06)',
          boxShadowSecondary: '0 14px 34px rgba(15, 23, 42, 0.08)',
          colorBgElevated: '#ffffff',
        },
        components: {
          Button: {
            controlHeight: 32,
            fontWeight: 600,
          },
          Card: {
            borderRadiusLG: 14,
          },
          Input: {
            controlHeight: 32,
          },
          Select: {
            controlHeight: 32,
            optionSelectedColor: 'var(--sd-color-primary-strong)',
            optionSelectedBg: 'var(--sd-color-primary-surface)',
          },
          InputNumber: {
            controlHeight: 32,
          },
          Tag: {
  
            fontSize: 10,
          },
          Table: {
            borderRadius: 12,
          },
        },
      }}
    >
      <AntdApp>
        <App />
      </AntdApp>
    </ConfigProvider>
  </StrictMode>,
)
