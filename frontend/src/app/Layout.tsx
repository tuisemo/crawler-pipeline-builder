import { Layout as AntdLayout, Menu } from 'antd'
import { HomeOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import type { MenuProps } from 'antd'

const { Sider, Content } = AntdLayout

const menuItems: MenuProps['items'] = [
  {
    key: '/',
    icon: <HomeOutlined />,
    label: '首页',
  },
  {
    key: '/tasks',
    icon: <UnorderedListOutlined />,
    label: '任务管理',
  },
]

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()

  // Hide sider for homepage (full-screen landing) and workbench routes
  const isFullScreenRoute = location.pathname === '/' || location.pathname.match(/^\/tasks\/[^/]+\/workbench$/)


  const selectedMenuKey = location.pathname === '/' ? '/' : '/tasks'

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
  }

  return (
    <AntdLayout style={{ minHeight: '100vh' }}>
      {!isFullScreenRoute && (
        <Sider
          width={200}
          style={{
            background: '#fff',
            borderRight: '1px solid rgba(148, 163, 184, 0.16)',
          }}
        >
          <div
            style={{
              height: 56,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderBottom: '1px solid rgba(148, 163, 184, 0.12)',
              fontWeight: 700,
              fontSize: 15,
              color: '#0f172a',
              letterSpacing: '-0.02em',
            }}
          >
            Crawler Workflow
          </div>
          <Menu
            mode="inline"
            selectedKeys={[selectedMenuKey]}
            items={menuItems}
            onClick={handleMenuClick}
            style={{
              border: 'none',
              padding: '8px 0',
            }}
          />
        </Sider>
      )}
      <AntdLayout>
        <Content
          style={{
            background: '#f3f7fb',
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </AntdLayout>
    </AntdLayout>
  )
}
