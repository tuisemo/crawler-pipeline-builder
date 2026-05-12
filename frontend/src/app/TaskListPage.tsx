import { useState, useEffect } from 'react'
import { Button, Space, Typography, Modal, Form, Input, message, Dropdown, Row, Col, Card, Statistic, Pagination } from 'antd'
import { 
  PlusOutlined, 
  MoreOutlined, 
  DeleteOutlined 
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { Task } from '../services/taskApi'
import { listTasks, createTask, deleteTask } from '../services/taskApi'

const { Title, Text } = Typography
const { TextArea } = Input

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

  useEffect(() => {
    let cancelled = false

    async function fetchTasks(page: number) {
      setLoading(true)
      try {
        const res = await listTasks(page, pageSize)
        if (!cancelled) {
          setTasks(res.items)
          setTotalTasks(res.total)
        }
      } catch {
        if (!cancelled) {
          message.error('加载任务列表失败')
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
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await createTask(values as { name: string; description?: string; target_url?: string })
      message.success('任务创建成功')
      setCreateModalOpen(false)
      form.resetFields()
      setCurrentPage(1)
      await listTasks(1, pageSize).then(res => {
        setTasks(res.items)
        setTotalTasks(res.total)
      })
    } catch {
      message.error('创建任务失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(taskId: number) {
    try {
      await deleteTask(taskId)
      message.success('任务已归档')
      await listTasks(currentPage, pageSize).then(res => {
        setTasks(res.items)
        setTotalTasks(res.total)
      })
    } catch {
      message.error('归档任务失败')
    }
  }

  return (
    <div className="command-center-container tech-blueprint-bg" style={{ minHeight: '100vh', padding: '0 0 60px 0' }}>
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 60px' }}>
        {/* --- Header Section --- */}
        <header style={{ padding: '40px 0 32px 0', borderBottom: 'var(--sd-border-subtle)', marginBottom: 40, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <Title level={2} style={{ color: 'var(--sd-color-text-primary)', margin: 0, fontSize: 32, fontWeight: 800, letterSpacing: '-0.02em' }}>
              任务调度中心
            </Title>
            <div className="mono" style={{ color: '#999', fontSize: 10, marginTop: 4 }}>数据记录: {totalTasks.toString().padStart(3, '0')} // 当前页码: {currentPage}</div>
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
              fontWeight: 600,
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
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 40 }}>
                {tasks.map((task) => (
                  <div 
                    key={task.id} 
                    className="tech-card-horizontal" 
                    onClick={() => navigate(`/tasks/${task.id}`)}
                    style={{ 
                      background: '#fff',
                      border: '1px solid #eee',
                      borderRadius: 12,
                      padding: '16px 24px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      position: 'relative',
                      overflow: 'hidden'
                    }}
                  >
                      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 24 }}>
                        <div className="mono" style={{ width: 40, color: '#ccc', fontSize: 11 }}>#{task.id.toString().padStart(3, '0')}</div>
                        
                        <div style={{ minWidth: 240 }}>
                          <div style={{ fontSize: 16, fontWeight: 700, color: '#000', marginBottom: 2 }}>{task.name}</div>
                          <div className="mono" style={{ fontSize: 10, color: '#999' }}>
                            来源标识: {task.target_url ? new URL(task.target_url).hostname : '本地数据集'}
                          </div>
                        </div>

                        <div style={{ flex: 1, paddingRight: 40 }}>
                          <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }} ellipsis={{ tooltip: task.description }}>
                            {task.description || '当前任务暂无业务逻辑描述...'}
                          </Text>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
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
                    <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, background: 'var(--sd-color-primary)', opacity: 0 }} className="hover-indicator" />
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
             <div style={{ position: 'sticky', top: 40 }}>
                <Card style={{ borderRadius: 12, border: '1px solid #eee', marginBottom: 20 }}>
                   <div className="mono" style={{ fontSize: 10, color: '#999', marginBottom: 16 }}>运行状态概览</div>
                   <Statistic title="活跃任务资源" value={tasks.filter(t=>t.status==='active').length} valueStyle={{ fontSize: 24, fontWeight: 800, color: 'var(--sd-color-success)' }} />
                   <div style={{ marginTop: 20, fontSize: 11, color: '#888' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                         <span>核心组件状态</span>
                         <span style={{ color: 'var(--sd-color-success)' }}>运行正常</span>
                      </div>
                      <div style={{ height: 2, background: '#f5f5f5', borderRadius: 1 }}>
                         <div style={{ width: '92%', height: '100%', background: 'var(--sd-color-primary)' }} />
                      </div>
                   </div>
                </Card>

                <div style={{ background: 'rgba(0,0,0,0.02)', padding: 20, borderRadius: 12, border: '1px dashed #eee' }}>
                   <div className="mono" style={{ fontSize: 10, color: '#bbb', marginBottom: 12 }}>快速操作指引</div>
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
        title={<span className="mono" style={{ letterSpacing: '0.1em', fontWeight: 700 }}>初始化采集任务</span>}
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
