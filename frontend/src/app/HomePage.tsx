import { Card, Typography, Space } from 'antd'
import { RocketOutlined } from '@ant-design/icons'

const { Title, Text } = Typography

export default function HomePage() {
  return (
    <div style={{ padding: 32 }}>
      <Card
        style={{
          maxWidth: 600,
          margin: '0 auto',
          borderRadius: 16,
          boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 12px 24px rgba(15, 23, 42, 0.05)',
        }}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <RocketOutlined style={{ fontSize: 32, color: '#2563eb' }} />
            <Title level={2} style={{ margin: 0, letterSpacing: '-0.02em' }}>
              欢迎使用爬虫工作流
            </Title>
          </div>
          <Text type="secondary" style={{ fontSize: 14 }}>
            使用可视化工作流设计器构建浏览器自动化爬虫 pipelines
          </Text>
          <Space direction="vertical" size={8}>
            <Text>
              1. 在「任务管理」中创建新任务
            </Text>
            <Text>
              2. 进入工作台设计爬取流程
            </Text>
            <Text>
              3. 生成并运行脚本
            </Text>
          </Space>
        </Space>
      </Card>
    </div>
  )
}
