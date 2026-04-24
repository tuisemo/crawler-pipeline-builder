import { Button, Card, Flex, Tag, Typography } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { WorkflowNodeType } from '../workflowContracts'

export type PaletteItem = {
  type: WorkflowNodeType
  label: string
  detail: string
}

type NodePaletteProps = {
  items: PaletteItem[]
  onAddNode: (type: WorkflowNodeType) => void
}

export function NodePalette({ items, onAddNode }: NodePaletteProps) {
  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography.Text strong style={{ fontSize: 16, color: '#0f172a' }}>节点面板</Typography.Text>
          <Tag color="blue" style={{ fontSize: 11 }}>{items.length} 种节点</Tag>
        </div>
      }
      styles={{ body: { padding: '8px 0' } }}
      className="node-palette ant-node-palette-card"
      variant="outlined"
    >
      <Flex vertical style={{ width: '100%' }}>
        {items.map((item) => (
          <div
            key={item.type}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              padding: '10px 16px',
              cursor: 'pointer',
              transition: 'background 150ms',
              borderBottom: '1px solid #f1f5f9',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#f8fbff' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = '' }}
            onClick={() => onAddNode(item.type)}
          >
            <div style={{ flex: 1, minWidth: 0, marginRight: 8 }}>
              <Typography.Text code style={{ fontSize: 11, fontWeight: 700 }}>{item.type}</Typography.Text>
              <div style={{ marginTop: 2 }}>
                <Typography.Text style={{ color: '#0f172a', fontSize: 13, fontWeight: 600 }}>{item.label}</Typography.Text>
                <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: '2px 0 0', lineHeight: 1.4 }}>
                  {item.detail}
                </Typography.Paragraph>
              </div>
            </div>
            <Button
              type="text"
              size="small"
              icon={<PlusOutlined style={{ color: '#2563eb', fontSize: 14 }} />}
              onClick={(e) => {
                e.stopPropagation()
                onAddNode(item.type)
              }}
              style={{ flexShrink: 0 }}
            >
              添加
            </Button>
          </div>
        ))}
      </Flex>
      <Card size="small" style={{ margin: '12px 12px', background: '#f8fbff', border: '1px solid #dbeafe', borderRadius: 12 }}>
        <Typography.Text strong style={{ fontSize: 12, color: '#0f172a' }}>适用范围</Typography.Text>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: '4px 0 0', lineHeight: 1.4 }}>
          当前工作台聚焦列表抓取、字段抽取与受控浏览器验证链路。
        </Typography.Paragraph>
      </Card>
    </Card>
  )
}
