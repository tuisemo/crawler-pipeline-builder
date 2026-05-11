import { useParams, useNavigate } from 'react-router-dom'
import { Button, Card, Typography, Descriptions, Space, Tag } from 'antd'
import { ArrowLeftOutlined, EditOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/tasks')}
          >
            返回
          </Button>
          <Title level={3} style={{ margin: 0, letterSpacing: '-0.02em' }}>
            任务详情
          </Title>
        </div>

        <Card
          style={{
            borderRadius: 16,
            boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 12px 24px rgba(15, 23, 42, 0.05)',
          }}
        >
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="任务ID">{taskId}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color="blue">就绪</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="任务名称">示例任务</Descriptions.Item>
            <Descriptions.Item label="创建时间">2024-01-15</Descriptions.Item>
            <Descriptions.Item label="运行次数">0</Descriptions.Item>
            <Descriptions.Item label="最后运行">--</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card
          style={{
            borderRadius: 16,
            boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 12px 24px rgba(15, 23, 42, 0.05)',
          }}
        >
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Text strong>任务描述</Text>
            <Text type="secondary">
              这是一个基于浏览器自动化的工作流任务。
            </Text>
          </Space>
        </Card>

        <Button
          type="primary"
          icon={<EditOutlined />}
          size="large"
          onClick={() => navigate(`/tasks/${taskId}/workbench`)}
          style={{ alignSelf: 'flex-start' }}
        >
          进入工作台编辑
        </Button>
      </Space>
    </div>
  )
}
