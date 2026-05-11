import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Card, Typography, Descriptions, Space, Tag, List, Drawer, Form, Input, message, Empty } from 'antd'
import { ArrowLeftOutlined, EditOutlined, EnterOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { getTask, updateTask, type Task, type AssetMeta } from '../services/taskApi'

const { Title, Text } = Typography
const { TextArea } = Input

const statusTagColor: Record<string, string> = {
  draft: 'default',
  active: 'green',
  archived: 'red',
}

const statusLabel: Record<string, string> = {
  draft: '草稿',
  active: '进行中',
  archived: '已归档',
}

const assetTypeLabel: Record<string, string> = {
  workflow_graph: '工作流图',
  compile_plan: '编译计划',
  list_script: '列表脚本',
  prompt: '提示词',
  detail_batch_config: '批处理配置',
  detail_batch_script: '批处理脚本',
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleString('zh-CN')
}

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const [task, setTask] = useState<Task | null>(null)
  const [assets, setAssets] = useState<AssetMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [editDrawerOpen, setEditDrawerOpen] = useState(false)
  const [editForm] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const id = taskId ? parseInt(taskId, 10) : NaN

  const fetchTask = useCallback(async () => {
    if (isNaN(id)) return
    setLoading(true)
    try {
      const detail = await getTask(id)
      setTask(detail.task)
      setAssets(detail.assets)
    } catch {
      message.error('加载任务详情失败')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchTask()
  }, [fetchTask])

  async function handleEdit() {
    if (!task) return
    try {
      const values = await editForm.validateFields()
      setSubmitting(true)
      const updated = await updateTask(task.id, values as { name?: string; description?: string; target_url?: string })
      setTask(updated.task)
      setEditDrawerOpen(false)
      message.success('任务更新成功')
    } catch {
      message.error('更新任务失败')
    } finally {
      setSubmitting(false)
    }
  }

  function openEditDrawer() {
    if (!task) return
    editForm.setFieldsValue({
      name: task.name,
      description: task.description,
      target_url: task.target_url,
    })
    setEditDrawerOpen(true)
  }

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/tasks')}>
              返回列表
            </Button>
            <Title level={3} style={{ margin: 0, letterSpacing: '-0.02em' }}>
              任务详情
            </Title>
          </Space>
          <Button icon={<EditOutlined />} onClick={openEditDrawer}>
            编辑信息
          </Button>
        </div>

        {/* Task Metadata Card */}
        <Card
          loading={loading}
          style={{
            borderRadius: 16,
            boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 12px 24px rgba(15, 23, 42, 0.05)',
          }}
        >
          {task && (
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="任务名称">{task.name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusTagColor[task.status] || 'default'}>
                  {statusLabel[task.status] || task.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="目标网址">
                {task.target_url || <Text type="secondary">--</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDate(task.created_at)}</Descriptions.Item>
              <Descriptions.Item label="任务描述" span={2}>
                {task.description || <Text type="secondary">无</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="最后更新">{formatDate(task.updated_at)}</Descriptions.Item>
              <Descriptions.Item label="任务ID">{task.id}</Descriptions.Item>
            </Descriptions>
          )}
        </Card>

        {/* Asset Overview Card */}
        <Card
          title={<Text strong style={{ fontSize: 15 }}>资产概览</Text>}
          loading={loading}
          style={{
            borderRadius: 16,
            boxShadow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 12px 24px rgba(15, 23, 42, 0.05)',
          }}
        >
          {assets.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<Text type="secondary">暂无已保存的资产</Text>}
            />
          ) : (
            <List
              size="small"
              dataSource={assets}
              renderItem={(asset) => (
                <List.Item
                  style={{ padding: '10px 0' }}
                  extra={
                    <Space direction="vertical" size={2} style={{ textAlign: 'right' }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        v{asset.version}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {formatDate(asset.created_at)}
                      </Text>
                    </Space>
                  }
                >
                  <Space>
                    <CheckCircleOutlined style={{ color: '#16a34a' }} />
                    <Text strong>{assetTypeLabel[asset.asset_type] || asset.asset_type}</Text>
                    <Tag color="blue" style={{ marginLeft: 4 }}>{asset.asset_type}</Tag>
                  </Space>
                </List.Item>
              )}
            />
          )}
        </Card>

        {/* Navigation Button */}
        <Button
          type="primary"
          icon={<EnterOutlined />}
          size="large"
          onClick={() => navigate(`/tasks/${taskId}/workbench`)}
          style={{
            alignSelf: 'flex-start',
            background: '#2563eb',
            borderColor: '#2563eb',
          }}
        >
          进入编排工作台
        </Button>
      </Space>

      {/* Edit Drawer */}
      <Drawer
        title="编辑任务信息"
        placement="right"
        width={400}
        open={editDrawerOpen}
        onClose={() => setEditDrawerOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setEditDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={submitting} onClick={handleEdit}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="任务名称"
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="请输入任务名称" />
          </Form.Item>
          <Form.Item name="description" label="任务描述">
            <TextArea rows={3} placeholder="请输入任务描述（可选）" />
          </Form.Item>
          <Form.Item name="target_url" label="目标网址">
            <Input placeholder="请输入目标网址（可选）" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  )
}
