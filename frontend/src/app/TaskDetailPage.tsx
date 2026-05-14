import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Typography, Space, Tag, Drawer, Form, Input, message, Empty, Breadcrumb, Result } from 'antd'
import { EditOutlined, EnterOutlined, CheckCircleOutlined, CodeOutlined, ShareAltOutlined } from '@ant-design/icons'
import { getTask, updateTask, type Task, type AssetMeta, UnauthorizedError, NotFoundError } from '../services/taskApi'
import './TaskDetailPage.css'

const { Title } = Typography
const { TextArea } = Input

const assetTypeLabel: Record<string, string> = {
  workflow_graph: '工作流图',
  compile_plan: '编译计划',
  list_script: '列表脚本',
  prompt: '提示词',
  detail_batch_config: '批处理配置',
  detail_batch_script: '批处理脚本',
}

function getTargetHostLabel(targetUrl: string | null): string {
  if (!targetUrl) {
    return '本地'
  }
  try {
    return new URL(targetUrl).hostname || targetUrl
  } catch {
    return targetUrl
  }
}

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const [task, setTask] = useState<Task | null>(null)
  const [assets, setAssets] = useState<AssetMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [notFound, setNotFound] = useState(false)
  const [editDrawerOpen, setEditDrawerOpen] = useState(false)
  const [editForm] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  const id = taskId ? parseInt(taskId, 10) : NaN

  useEffect(() => {
    let cancelled = false

    async function fetchTask() {
      if (isNaN(id)) {
        setTask(null)
        setAssets([])
        setNotFound(true)
        return
      }
      setLoading(true)
      setNotFound(false)
      try {
        const detail = await getTask(id)
        if (!cancelled) {
          setTask(detail.task)
          setAssets(detail.assets)
        }
      } catch (err) {
        if (!cancelled) {
          // Detect 404 / not-found (non-owned or non-existent task)
          if (err instanceof NotFoundError) {
            setNotFound(true)
          } else if (err instanceof UnauthorizedError) {
            // 401 handled by apiClient onUnauthorized
            message.error('登录已过期，请重新登录')
          } else {
            message.error('加载任务详情失败')
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchTask()

    return () => {
      cancelled = true
    }
  }, [id])

  async function handleEdit() {
    if (!task) return
    let values: { name?: string; description?: string; target_url?: string }
    try {
      values = await editForm.validateFields()
    } catch {
      return
    }

    setSubmitting(true)
    try {
      const updated = await updateTask(task.id, values)
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

  if (notFound) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '80vh', background: '#fff' }}>
        <Result
          status="404"
          title="任务不存在"
          subTitle="该任务可能已被删除，或者您没有访问权限。"
          extra={
            <Button type="primary" onClick={() => navigate('/tasks')} style={{ background: '#000', border: 'none', borderRadius: 8 }}>
              返回任务列表
            </Button>
          }
        />
      </div>
    )
  }

  if (loading && !task) {
    return (
      <div style={{ padding: 100, textAlign: 'center', background: '#fff' }}>
        <div className="mono" style={{ color: 'var(--sd-color-primary)', fontSize: 14 }}>同步工作空间资源...</div>
      </div>
    )
  }

  return (
    <div className="tech-workspace">
      {/* --- Left Sidebar (Command Unit) --- */}
      <div className="tech-sidebar">
        <Breadcrumb
          items={[
            { title: <a onClick={() => navigate('/tasks')} style={{ color: '#999' }}>任务列表</a> },
            { title: <span className="mono" style={{ color: '#000' }}>#{task?.id.toString().padStart(3, '0')}</span> },
          ]}
          style={{ marginBottom: 40 }}
        />

        <div style={{ marginBottom: 32 }}>
           <div className="mono" style={{ color: '#bbb', fontSize: 12, letterSpacing: '0.1em', marginBottom: 12 }}>任务标识符 // IDENTIFIER</div>
           <Title level={2} style={{ margin: 0, fontSize: 28, letterSpacing: '-0.02em' }}>{task?.name}</Title>
           <Tag color={task?.status === 'active' ? 'success' : 'default'} style={{ marginTop: 12, borderRadius: 4 }}>
             {task?.status === 'active' ? '● 正在运行' : '○ 待处理'}
           </Tag>
        </div>

        <div style={{ marginBottom: 32 }}>
           <div className="mono" style={{ color: '#bbb', fontSize: 12, letterSpacing: '0.1em', marginBottom: 16 }}>系统元数据 // METADATA</div>
           <Space orientation="vertical" size={16} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed #eee', paddingBottom: 8 }}>
                <span style={{ color: '#999', fontSize: 12 }}>创建时间</span>
                <span className="mono" style={{ fontSize: 12 }}>{task ? new Date(task.created_at).toLocaleDateString() : '--'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed #eee', paddingBottom: 8 }}>
                <span style={{ color: '#999', fontSize: 12 }}>最后更新</span>
                <span className="mono" style={{ fontSize: 12 }}>{task ? new Date(task.updated_at).toLocaleDateString() : '--'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed #eee', paddingBottom: 8 }}>
                <span style={{ color: '#999', fontSize: 12 }}>目标域名</span>
                <span className="mono" style={{ fontSize: 12, color: 'var(--sd-color-info)' }}>{getTargetHostLabel(task?.target_url ?? null)}</span>
              </div>
           </Space>
        </div>

        <div style={{ marginTop: 'auto' }}>
           <Button 
            block 
            icon={<EditOutlined />} 
            onClick={openEditDrawer}
            style={{ height: 40, borderRadius: 8, marginBottom: 16 }}
           >
            修改任务配置
           </Button>
           <Button 
            block 
            type="primary"
            icon={<EnterOutlined />} 
            onClick={() => navigate(`/tasks/${taskId}/workbench`)}
            style={{ height: 40, borderRadius: 8, background: '#000', border: 'none' }}
           >
            进入流程工作站
           </Button>
        </div>
      </div>

      {/* --- Main Dashboard Area --- */}
      <div className="tech-main">
         <div style={{ maxWidth: 1000, margin: '0 auto' }}>
            {/* Description Block */}
            <section style={{ marginBottom: 60 }}>
               <div className="mono" style={{ color: 'var(--sd-color-primary)', fontSize: 12, marginBottom: 20, letterSpacing: '0.1em' }}>
                 // 业务逻辑描述 / DESCRIPTION
               </div>
                <div className="task-description-block">
                  {task?.description || '暂无该任务的详细业务描述。您可以通过“修改任务配置”添加相关背景。'}
                </div>
            </section>

            {/* Assets List Section */}
            <section>
               <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32, paddingBottom: 16, borderBottom: '2px solid #000' }}>
                  <div className="mono" style={{ fontSize: 14 }}>
                    存储资产库 ({assets.length}) <span style={{ color: '#ccc', fontWeight: 400, marginLeft: 8 }}>/ REPOSITORY_ASSETS</span>
                  </div>
                  <Space>
                    <Button type="text" icon={<CodeOutlined />} />
                    <Button type="text" icon={<ShareAltOutlined />} />
                  </Space>
               </div>

               {assets.length === 0 ? (
                 <div style={{ padding: '80px 0', textAlign: 'center', background: '#fafafa', borderRadius: 16, border: '1px dashed #ddd' }}>
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span style={{ color: '#999' }}>暂未检测到已编译资产</span>} />
                 </div>
               ) : (
                 <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {assets.map((asset, idx) => (
                      <div key={idx} className="tech-card-horizontal">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                           <div className="asset-icon-wrapper">
                              <CheckCircleOutlined style={{ color: 'var(--sd-color-success)', fontSize: 18 }} />
                           </div>
                           <div>
                              <div style={{ fontSize: 16, color: '#000' }}>{assetTypeLabel[asset.asset_type] || asset.asset_type}</div>
                              <div className="mono" style={{ fontSize: 12, color: '#bbb', marginTop: 2 }}>{asset.asset_type.toUpperCase()}</div>
                           </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                           <div className="mono" style={{ fontSize: 14, color: 'var(--sd-color-primary)' }}>REV_{asset.version.toString().padStart(2, '0')}</div>
                           <div className="mono" style={{ fontSize: 12, color: '#ccc', marginTop: 4 }}>{new Date(asset.created_at).toLocaleDateString()}</div>
                        </div>
                      </div>
                    ))}
                 </div>
               )}
            </section>
         </div>
      </div>

      {/* --- Edit Configuration Drawer --- */}
      <Drawer
        title={<span className="mono">配置更新 / EDIT_CONFIG</span>}
        placement="right"
        size="480"
        open={editDrawerOpen}
        onClose={() => setEditDrawerOpen(false)}
        styles={{ body: { padding: '32px' } }}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label={<span className="mono" style={{ fontSize: 12 }}>任务识别名 / TASK_NAME</span>}
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0', fontSize: 16 }} />
          </Form.Item>
          <Form.Item name="description" label={<span className="mono" style={{ fontSize: 12 }}>业务背景 / DESCRIPTION</span>}>
            <TextArea rows={5} bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
          <Form.Item name="target_url" label={<span className="mono" style={{ fontSize: 12 }}>目标起始地址 / TARGET_URL</span>}>
            <Input bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
          
          <div style={{ marginTop: 40 }}>
            <Button type="primary" block size="large" loading={submitting} onClick={handleEdit} style={{ height: 54, background: '#000', border: 'none', borderRadius: 8 }}>
              保存并部署更新
            </Button>
          </div>
        </Form>
      </Drawer>
    </div>
  )
}
