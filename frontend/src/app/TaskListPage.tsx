import { useState, useEffect, useCallback } from 'react'
import { Button, Table, Tag, Space, Typography, Card, Modal, Form, Input, Drawer, Popconfirm, Select, message } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, EnterOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { Task } from '../services/taskApi'
import { listTasks, createTask, updateTask, deleteTask } from '../services/taskApi'

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

export default function TaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editDrawerOpen, setEditDrawerOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listTasks(1, 100)
      setTasks(res.items)
    } catch {
      message.error('加载任务列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  const filteredTasks = statusFilter
    ? tasks.filter((t) => t.status === statusFilter)
    : tasks

  async function handleCreate() {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await createTask(values as { name: string; description?: string; target_url?: string })
      message.success('任务创建成功')
      setCreateModalOpen(false)
      form.resetFields()
      await fetchTasks()
    } catch (err) {
      message.error('创建任务失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleEdit() {
    if (!editingTask) return
    try {
      const values = await editForm.validateFields()
      setSubmitting(true)
      await updateTask(editingTask.id, values as { name?: string; description?: string; target_url?: string })
      message.success('任务更新成功')
      setEditDrawerOpen(false)
      setEditingTask(null)
      editForm.resetFields()
      await fetchTasks()
    } catch {
      message.error('更新任务失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(taskId: number) {
    try {
      await deleteTask(taskId)
      message.success('任务已删除')
      await fetchTasks()
    } catch {
      message.error('删除任务失败')
    }
  }

  function openEditDrawer(task: Task) {
    setEditingTask(task)
    editForm.setFieldsValue({
      name: task.name,
      description: task.description,
      target_url: task.target_url,
    })
    setEditDrawerOpen(true)
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: Task) => (
        <a
          onClick={() => navigate(`/tasks/${record.id}`)}
          style={{ cursor: 'pointer' }}
        >
          {name}
        </a>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc: string | null) => desc ? <Text type="secondary">{desc}</Text> : <Text type="secondary" style={{ color: '#94a3b8' }}>无</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: Task['status']) => (
        <Tag color={statusTagColor[status] || 'default'}>{statusLabel[status] || status}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (ts: string) => new Date(ts).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: Task) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditDrawer(record)}
          >
            编辑
          </Button>
          <Button
            size="small"
            icon={<EnterOutlined />}
            onClick={() => navigate(`/tasks/${record.id}/workbench`)}
          >
            进入
          </Button>
          <Popconfirm
            title="确定要删除该任务吗？"
            description="删除后任务将进入归档状态"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
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
        <div
          style={{
            marginBottom: 20,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Space size={12}>
            <Title level={4} style={{ margin: 0, letterSpacing: '-0.02em' }}>
              任务列表
            </Title>
            <Select
              allowClear
              placeholder="状态筛选"
              style={{ width: 120 }}
              value={statusFilter}
              onChange={setStatusFilter}
              options={[
                { label: '草稿', value: 'draft' },
                { label: '进行中', value: 'active' },
                { label: '已归档', value: 'archived' },
              ]}
            />
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新建任务
          </Button>
        </div>

        <Table<Task>
          dataSource={filteredTasks}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* Create Modal */}
      <Modal
        title="新建任务"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false)
          form.resetFields()
        }}
        okText="创建"
        cancelText="取消"
        confirmLoading={submitting}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
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
      </Modal>

      {/* Edit Drawer */}
      <Drawer
        title="编辑任务"
        placement="right"
        width={400}
        open={editDrawerOpen}
        onClose={() => {
          setEditDrawerOpen(false)
          setEditingTask(null)
          editForm.resetFields()
        }}
        extra={
          <Space>
            <Button
              onClick={() => {
                setEditDrawerOpen(false)
                setEditingTask(null)
                editForm.resetFields()
              }}
            >
              取消
            </Button>
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
