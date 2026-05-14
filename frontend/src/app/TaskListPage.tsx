import { useState, useEffect, useRef } from 'react'
import { Button, Space, Typography, Modal, Form, Input, message, Dropdown, Row, Col, Card, Statistic, Pagination } from 'antd'
import { 
  PlusOutlined, 
  MoreOutlined, 
  DeleteOutlined 
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { Task } from '../services/taskApi'
import { listTasks, createTask, deleteTask } from '../services/taskApi'
import './TaskListPage.css'

const { Title, Text } = Typography
const { TextArea } = Input

function getTaskSourceLabel(targetUrl: string | null): string {
  if (!targetUrl) {
    return '本地数据集'
  }
  try {
    return new URL(targetUrl).hostname || targetUrl
  } catch {
    return targetUrl
  }
}

export default function TaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<Task[]>([])
  const [totalTasks, setTotalTasks] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize] = useState(10) // Single column list, 10 items
  const [loading, setLoading] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const pendingRefreshFailureMessageRef = useRef<string | null>(null)
  const lastLoadedPageRef = useRef(currentPage)
  const skipNextFetchPageRef = useRef<number | null>(null)
  const pageCacheRef = useRef<Record<number, { items: Task[]; total: number }>>({})

  async function refreshTasks(page: number) {
    const res = await listTasks(page, pageSize)
    pageCacheRef.current[page] = { items: res.items, total: res.total }
    lastLoadedPageRef.current = page
    setTasks(res.items)
    setTotalTasks(res.total)
  }

  useEffect(() => {
    if (skipNextFetchPageRef.current === currentPage) {
      skipNextFetchPageRef.current = null
      return
    }

    let cancelled = false

    async function fetchTasks(page: number) {
      setLoading(true)
      try {
        const res = await listTasks(page, pageSize)
        if (!cancelled) {
          pendingRefreshFailureMessageRef.current = null
          lastLoadedPageRef.current = page
          pageCacheRef.current[page] = { items: res.items, total: res.total }
          setTasks(res.items)
          setTotalTasks(res.total)
        }
      } catch {
        if (!cancelled) {
          if (page !== lastLoadedPageRef.current) {
            setCurrentPage(lastLoadedPageRef.current)
          }
          const pendingMessage = pendingRefreshFailureMessageRef.current
          pendingRefreshFailureMessageRef.current = null
          if (pendingMessage) {
            message.warning(pendingMessage)
          } else {
            message.error('加载任务列表失败')
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchTasks(currentPage)

    return () => {
      cancelled = true
    }
  }, [currentPage, pageSize])

  async function handleCreate() {
    let values: { name: string; description?: string; target_url?: string }
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    setSubmitting(true)
    try {
      await createTask(values)
    } catch {
      message.error('创建任务失败')
      setSubmitting(false)
      return
    }

    try {
      message.success('任务创建成功')
      setCreateModalOpen(false)
      form.resetFields()

      if (currentPage !== 1) {
        pendingRefreshFailureMessageRef.current = '任务已创建，但列表刷新失败'
        setCurrentPage(1)
        return
      }

      await refreshTasks(1)
    } catch {
      message.warning('任务已创建，但列表刷新失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(taskId: number) {
    try {
      await deleteTask(taskId)
    } catch {
      message.error('归档任务失败')
      return
    }

    const nextPage = tasks.length === 1 && currentPage > 1 ? currentPage - 1 : currentPage
    const expectedTotalTasks = Math.max(0, totalTasks - 1)

    try {
      message.success('任务已归档')

      if (nextPage !== currentPage) {
        try {
          const res = await listTasks(nextPage, pageSize)
          pageCacheRef.current[nextPage] = { items: res.items, total: res.total }
          lastLoadedPageRef.current = nextPage
          skipNextFetchPageRef.current = nextPage
          setTasks(res.items)
          setTotalTasks(res.total)
          setCurrentPage(nextPage)
          return
        } catch {
          const cachedPage = pageCacheRef.current[nextPage]
          if (cachedPage) {
            skipNextFetchPageRef.current = nextPage
            lastLoadedPageRef.current = nextPage
            setTasks(cachedPage.items)
            setTotalTasks(expectedTotalTasks)
            setCurrentPage(nextPage)
          } else {
            skipNextFetchPageRef.current = nextPage
            lastLoadedPageRef.current = nextPage
            setTasks([])
            setTotalTasks(expectedTotalTasks)
            setCurrentPage(nextPage)
          }
          message.warning('任务已归档，但列表刷新失败')
          return
        }
      }

      await refreshTasks(nextPage)
    } catch {
      message.warning('任务已归档，但列表刷新失败')
    }
  }

  return (
    <div className="command-center-container tech-blueprint-bg">
      <div className="task-list-wrapper">
        {/* --- Header Section --- */}
        <header className="task-list-header">
          <div>
            <Title level={2} style={{ color: 'var(--sd-color-text-primary)', margin: 0, fontSize: 32, letterSpacing: '-0.02em' }}>
              任务调度中心
            </Title>
            <div className="mono" style={{ color: '#999', fontSize: 12, marginTop: 4 }}>数据记录: {totalTasks.toString().padStart(3, '0')} // 当前页码: {currentPage}</div>
          </div>
          <Button 
            type="primary" 
            icon={<PlusOutlined />} 
            onClick={() => setCreateModalOpen(true)}
            style={{ 
              background: '#000', 
              color: '#fff', 
              border: 'none', 
              height: 42, 
              padding: '0 24px',
              borderRadius: 6
            }}
          >
            开启新任务
          </Button>
        </header>

        <Row gutter={48}>
          {/* Compact Task List (Left) */}
          <Col span={18}>
            {loading && tasks.length === 0 ? (
              <div style={{ color: 'var(--sd-color-text-tertiary)', textAlign: 'center', padding: 100 }} className="mono">
                正在同步系统资源...
              </div>
            ) : (
              <div className="task-list-items">
                {tasks.map((task) => (
                  <div 
                    key={task.id} 
                    className="task-card-horizontal" 
                    onClick={() => navigate(`/tasks/${task.id}`)}
                  >
                      <div className="task-card-content">
                        <div className="mono task-id-badge">#{task.id.toString().padStart(3, '0')}</div>
                        
                        <div className="task-info">
                          <div className="task-title">{task.name}</div>
                          <div className="mono task-source">
                            来源标识: {getTaskSourceLabel(task.target_url)}
                          </div>
                        </div>

                        <div className="task-description">
                          <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }} ellipsis={{ tooltip: task.description }}>
                            {task.description || '当前任务暂无业务逻辑描述...'}
                          </Text>
                        </div>
                      </div>

                      <div className="task-actions">
                        <Space>
                          <span className={`glowing-dot ${task.status === 'active' ? 'success' : 'warning'}`} />
                          <span style={{ fontSize: 13, fontWeight: 500, color: task.status === 'active' ? 'var(--sd-color-success)' : '#999' }}>
                            {task.status === 'active' ? '正常运行' : '待处理'}
                          </span>
                        </Space>
                      
                      <Dropdown
                        menu={{
                          items: [
                            { key: 'delete', label: '归档删除', danger: true, icon: <DeleteOutlined />, onClick: (e) => { e.domEvent.stopPropagation(); handleDelete(task.id) } }
                          ]
                        }}
                        trigger={['click']}
                      >
                        <Button 
                          type="text" 
                          icon={<MoreOutlined style={{ color: '#ccc' }} />} 
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Dropdown>
                    </div>

                    {/* Subtle hover indicator */}
                    <div className="hover-indicator" />
                  </div>
                ))}
                
                {tasks.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '60px 0', border: '1px dashed #eee', borderRadius: 12 }}>
                    <Text type="secondary">暂无任务数据</Text>
                  </div>
                )}
              </div>
            )}

            {/* Pagination */}
            <div style={{ display: 'flex', justifyContent: 'center', paddingBottom: 40 }}>
              <Pagination 
                current={currentPage} 
                total={totalTasks} 
                pageSize={pageSize} 
                onChange={(page) => setCurrentPage(page)}
                showSizeChanger={false}
                size="small"
              />
            </div>
          </Col>

          {/* Side Info (Right) */}
          <Col span={6}>
             <div className="sticky-info-col">
                <Card style={{ borderRadius: 12, border: '1px solid #eee', marginBottom: 20 }}>
                   <div className="mono" style={{ fontSize: 12, color: '#999', marginBottom: 16 }}>运行状态概览</div>
                   <Statistic title="活跃任务资源" value={tasks.filter(t=>t.status==='active').length} valueStyle={{ fontSize: 24, color: 'var(--sd-color-success)' }} />
                   <div style={{ marginTop: 20, fontSize: 12, color: '#888' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                         <span>核心组件状态</span>
                         <span style={{ color: 'var(--sd-color-success)' }}>运行正常</span>
                      </div>
                      <div className="progress-bar-track">
                         <div className="progress-bar-fill" />
                      </div>
                   </div>
                </Card>

                <div className="quick-guide-box">
                   <div className="mono" style={{ fontSize: 12, color: '#bbb', marginBottom: 12 }}>快速操作指引</div>
                   <div style={{ fontSize: 12, color: '#888', lineHeight: 1.6 }}>
                      点击列表项可快速进入“工作站”，支持可视化流程编排与自动化部署。
                   </div>
                </div>
             </div>
          </Col>
        </Row>
      </div>

      {/* --- Create Modal --- */}
      <Modal
        title={<span className="mono" style={{ letterSpacing: '0.1em' }}>初始化采集任务</span>}
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false)
          form.resetFields()
        }}
        okText="立即部署"
        cancelText="暂不创建"
        confirmLoading={submitting}
        width={560}
        centered
        styles={{ body: { padding: '24px 0' } }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label={<span className="mono" style={{ fontSize: 12 }}>任务唯一标识</span>}
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="例如: 电商资产采集_V1" bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0', fontSize: 16 }} />
          </Form.Item>
          <Form.Item name="description" label={<span className="mono" style={{ fontSize: 12 }}>业务逻辑描述</span>}>
            <TextArea rows={3} placeholder="简述该任务的采集逻辑与业务目标..." bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
          <Form.Item name="target_url" label={<span className="mono" style={{ fontSize: 12 }}>目标起始地址</span>}>
            <Input placeholder="https://example.com" bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
