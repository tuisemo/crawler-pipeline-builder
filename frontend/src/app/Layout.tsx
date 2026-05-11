import { Layout as AntdLayout } from 'antd'
import { Outlet, useLocation } from 'react-router-dom'

const { Content } = AntdLayout

export default function Layout() {
  const location = useLocation()

  // Hide sider for homepage and all task-related routes (we use custom layouts there)
  const isFullScreenRoute = location.pathname === '/' || location.pathname.startsWith('/tasks')

  return (
    <AntdLayout style={{ minHeight: '100vh', background: 'var(--sd-color-bg-base)' }}>
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
