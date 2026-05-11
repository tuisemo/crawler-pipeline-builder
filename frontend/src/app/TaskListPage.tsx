import { Button, Table, Tag, Space, Typography, Card } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const { Title } = Typography

// Mock data - will be replaced with actual API calls
const mockTasks = [
  { id: '1', name: '商品数据采集', status: 'ready', createdAt: '2024-01-15' },
  { id: '2', name: '新闻列表抓取', status: 'running', createdAt: '2024-01-14' },
  { id: '3', name: '评论数据采集', status: 'completed', createdAt: '2024-01-13' },
]

export default function TaskListPage() {
  const navigate = useNavigate()

  const columns = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: { id: string }) => (
        <a onClick={() => navigate(`/tasks/${record.id}`)} style={{ cursor: 'pointer' }}>
          {text}
        </a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const statusMap: Record<string, { color: string; label: string }> = {
          ready: { color: 'blue', label: '就绪' },
          running: { color: 'processing', label: '运行中' },
          completed: { color: 'success', label: '已完成' },
        }
        const config = statusMap[status] || { color: 'default', label: status }
        return <Tag color={config.color}>{config.label}</Tag>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: { id: string }) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/tasks/${record.id}`)}>
            查看
          </Button>
          <Button size="small" type="primary" onClick={() => navigate(`/tasks/${record.id}/workbench`)}>
            工作台
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Card
        style={{
          borderRadius: 16,
          boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 12px 24px rgba(15, 23, 42, 0.05)',
        }}
      >
        <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0, letterSpacing: '-0.02em' }}>
            任务列表
          </Title>
          <Button type="primary" icon={<PlusOutlined />}>
            新建任务
          </Button>
        </div>
        <Table
          dataSource={mockTasks}
          columns={columns}
          rowKey="id"
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  )
}
