import { Layout as AntdLayout, Button, Space, Typography, Avatar, Alert } from 'antd'
import { LogoutOutlined, UserOutlined } from '@ant-design/icons'
import { Outlet } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

const { Content, Header } = AntdLayout
const { Text } = Typography

function AppHeader() {
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: '-0.02em', color: '#000' }}>
            Scraper Flow Studio
          </span>
        </div>

        <Space size={12} align="center">
          {isLoading ? null : isAuthenticated && user ? (
            <>
              <Avatar size={28} icon={<UserOutlined />} style={{ backgroundColor: '#000' }} />
              <Text style={{ fontSize: 13, fontWeight: 500, color: '#333' }}>
                {user.display_name}
              </Text>
              <Button
                type="text"
                icon={<LogoutOutlined />}
                onClick={logout}
                style={{ fontSize: 13, color: '#666', padding: '0 8px', height: 32 }}
              >
                退出
              </Button>
            </>
          ) : (
            <Button
              type="primary"
              size="small"
              onClick={() => login(window.location.pathname)}
              style={{ height: 32, fontWeight: 600, borderRadius: 6 }}
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
    <AntdLayout style={{ minHeight: '100vh', background: 'var(--sd-color-bg-base)' }}>
      <AppHeader />
      <AntdLayout>
        <Content
          style={{
            background: 'var(--sd-color-bg-base)',
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </AntdLayout>
    </AntdLayout>
  )
}
