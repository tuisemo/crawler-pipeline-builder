import { Layout as AntdLayout, Button, Space, Typography, Avatar, Alert } from 'antd'
import { LogoutOutlined, UserOutlined } from '@ant-design/icons'
import { Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import logoUrl from '../../public/logo_128.webp'

const { Content, Header } = AntdLayout
const { Text } = Typography

function AppHeader() {
  const navigate = useNavigate()
  const { isAuthenticated, user, isLoading, login, logout, authError, clearAuthError } = useAuth()

  return (
    <>
      {authError && (
        <Alert
          message={authError}
          type="error"
          closable
          onClose={clearAuthError}
          style={{ borderRadius: 0, border: 'none', textAlign: 'center' }}
        />
      )}
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 32px',
          background: '#fff',
          borderBottom: '1px solid rgba(0, 0, 0, 0.06)',
          height: 52,
          lineHeight: '52px',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            onClick={() => navigate('/')}
            style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
          >
            <img
              src={logoUrl}
              alt="Scraper Flow Studio"
              style={{ width: 28, height: 28, objectFit: 'contain', borderRadius: 6 }}
            />
            <span style={{ 
              fontFamily: 'var(--sd-font-logo)', 
              letterSpacing: '-0.05em', 
              color: 'var(--sd-color-ink)', 
              fontSize: 18,
              display: 'flex',
              alignItems: 'baseline',
              gap: 5,
              textTransform: 'uppercase'
            }}>
              <span style={{ fontWeight: 800 }}>Scraper Flow</span>
              <span style={{ fontWeight: 400, opacity: 0.6, fontSize: 14 }}>Studio</span>
            </span>
          </div>
        </div>

        <Space size={12} align="center">
          {isLoading ? null : isAuthenticated && user ? (
            <>
              <Avatar size={24} icon={<UserOutlined />} style={{ backgroundColor: 'var(--sd-color-primary)' }} />
              <Text style={{ color: 'var(--sd-color-text-secondary)' }}>
                {user.display_name}
              </Text>
              <Button
                type="text"
                icon={<LogoutOutlined />}
                onClick={logout}
                style={{ color: 'var(--sd-color-text-tertiary)', padding: '0 8px' }}
              >
                退出
              </Button>
            </>
          ) : (
            <Button
              type="primary"
              size="small"
              onClick={() => login(window.location.hash.replace('#', '') || '/')}
            >
              登录
            </Button>
          )}
        </Space>
      </Header>
    </>
  )
}

export default function Layout() {
  return (
    <AntdLayout style={{ height: '100vh', background: 'var(--sd-color-bg-base)', overflow: 'hidden' }}>
      <AppHeader />
      <AntdLayout style={{ height: 'calc(100vh - 52px)', overflow: 'hidden' }}>
        <Content
          id="main-content"
          style={{
            background: 'var(--sd-color-bg-base)',
            height: '100%',
            overflowY: 'auto',
            position: 'relative',
          }}
        >
          <Outlet />
        </Content>
      </AntdLayout>
    </AntdLayout>
  )
}
