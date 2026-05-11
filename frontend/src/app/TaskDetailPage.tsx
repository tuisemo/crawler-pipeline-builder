import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Typography, Space, Tag, List, Drawer, Form, Input, message, Empty, Breadcrumb } from 'antd'
import { ArrowLeftOutlined, EditOutlined, EnterOutlined, CheckCircleOutlined, CodeOutlined, ShareAltOutlined } from '@ant-design/icons'
import { getTask, updateTask, type Task, type AssetMeta } from '../services/taskApi'

const { Title, Text } = Typography
const { TextArea } = Input

const assetTypeLabel: Record<string, string> = {
  workflow_graph: '工作流图',
  compile_plan: '编译计划',
  list_script: '列表脚本',
  prompt: '提示词',
  detail_batch_config: '批处理配置',
  detail_batch_script: '批处理脚本',
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

  if (loading && !task) {
    return (
      <div style={{ padding: 100, textAlign: 'center', background: '#fff' }}>
        <div className="mono" style={{ color: 'var(--sd-color-primary)', fontSize: 14 }}>同步工作空间资源...</div>
      </div>
    )
  }

  return (
    <div className="tech-workspace" style={{ background: '#fff' }}>
      {/* --- Left Sidebar (Command Unit) --- */}
      <div className="tech-sidebar" style={{ 
        width: 360, 
        borderRight: '1px solid #f0f0f0', 
        padding: '40px 32px',
        display: 'flex',
        flexDirection: 'column',
        background: '#fdfdfd'
      }}>
        <Breadcrumb
          items={[
            { title: <a onClick={() => navigate('/tasks')} style={{ color: '#999' }}>任务列表</a> },
            { title: <span className="mono" style={{ color: '#000', fontWeight: 600 }}>#{task?.id.toString().padStart(3, '0')}</span> },
          ]}
          style={{ marginBottom: 40 }}
        />

        <div style={{ marginBottom: 48 }}>
           <div className="mono" style={{ color: '#bbb', fontSize: 10, letterSpacing: '0.1em', marginBottom: 12 }}>任务标识符 // IDENTIFIER</div>
           <Title level={2} style={{ margin: 0, fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>{task?.name}</Title>
           <Tag color={task?.status === 'active' ? 'success' : 'default'} style={{ marginTop: 12, borderRadius: 4, fontWeight: 600 }}>
             {task?.status === 'active' ? '● 正在运行' : '○ 待处理'}
           </Tag>
        </div>

        <div style={{ marginBottom: 48 }}>
           <div className="mono" style={{ color: '#bbb', fontSize: 10, letterSpacing: '0.1em', marginBottom: 16 }}>系统元数据 // METADATA</div>
           <Space direction="vertical" size={16} style={{ width: '100%' }}>
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
                <span className="mono" style={{ fontSize: 12, color: 'var(--sd-color-info)' }}>{task?.target_url ? new URL(task.target_url).hostname : '本地'}</span>
              </div>
           </Space>
        </div>

        <div style={{ marginTop: 'auto' }}>
           <Button 
            block 
            icon={<EditOutlined />} 
            onClick={openEditDrawer}
            style={{ height: 48, borderRadius: 8, marginBottom: 16, fontWeight: 600 }}
           >
            修改任务配置
           </Button>
           <Button 
            block 
            type="primary"
            icon={<EnterOutlined />} 
            onClick={() => navigate(`/tasks/${taskId}/workbench`)}
            style={{ height: 48, borderRadius: 8, background: '#000', border: 'none', fontWeight: 700 }}
           >
            进入流程工作站
           </Button>
        </div>
      </div>

      {/* --- Main Dashboard Area --- */}
      <div className="tech-main" style={{ flex: 1, padding: '60px 80px', overflowY: 'auto' }}>
         <div style={{ maxWidth: 1000, margin: '0 auto' }}>
            {/* Description Block */}
            <section style={{ marginBottom: 60 }}>
               <div className="mono" style={{ color: 'var(--sd-color-primary)', fontSize: 11, fontWeight: 700, marginBottom: 20, letterSpacing: '0.1em' }}>
                 // 业务逻辑描述 / DESCRIPTION
               </div>
               <div style={{ 
                 background: '#f9f9f9', 
                 padding: 32, 
                 borderRadius: 16, 
                 border: '1px solid #f0f0f0',
                 color: '#555',
                 fontSize: 16,
                 lineHeight: 1.8,
                 whiteSpace: 'pre-wrap'
               }}>
                 {task?.description || '暂无该任务的详细业务描述。您可以通过“修改任务配置”添加相关背景。'}
               </div>
            </section>

            {/* Assets List Section */}
            <section>
               <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32, paddingBottom: 16, borderBottom: '2px solid #000' }}>
                  <div className="mono" style={{ fontSize: 14, fontWeight: 800 }}>
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
                      <div key={idx} className="tech-card-horizontal" style={{ 
                        background: '#fff', 
                        border: '1px solid #eee', 
                        borderRadius: 12, 
                        padding: '20px 32px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        transition: 'all 0.2s ease'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                           <div style={{ width: 40, height: 40, background: 'rgba(0,0,0,0.02)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              <CheckCircleOutlined style={{ color: 'var(--sd-color-success)', fontSize: 18 }} />
                           </div>
                           <div>
                              <div style={{ fontSize: 16, fontWeight: 700, color: '#000' }}>{assetTypeLabel[asset.asset_type] || asset.asset_type}</div>
                              <div className="mono" style={{ fontSize: 10, color: '#bbb', marginTop: 2 }}>{asset.asset_type.toUpperCase()}</div>
                           </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                           <div className="mono" style={{ fontSize: 14, fontWeight: 700, color: 'var(--sd-color-primary)' }}>REV_{asset.version.toString().padStart(2, '0')}</div>
                           <div className="mono" style={{ fontSize: 11, color: '#ccc', marginTop: 4 }}>{new Date(asset.created_at).toLocaleDateString()}</div>
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
        title={<span className="mono" style={{ fontWeight: 700 }}>配置更新 / EDIT_CONFIG</span>}
        placement="right"
        width={480}
        open={editDrawerOpen}
        onClose={() => setEditDrawerOpen(false)}
        styles={{ body: { padding: '32px' } }}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label={<span className="mono" style={{ fontSize: 11 }}>任务识别名 / TASK_NAME</span>}
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0', fontSize: 16 }} />
          </Form.Item>
          <Form.Item name="description" label={<span className="mono" style={{ fontSize: 11 }}>业务背景 / DESCRIPTION</span>}>
            <TextArea rows={5} bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
          <Form.Item name="target_url" label={<span className="mono" style={{ fontSize: 11 }}>目标起始地址 / TARGET_URL</span>}>
            <Input bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
          
          <div style={{ marginTop: 40 }}>
            <Button type="primary" block size="large" loading={submitting} onClick={handleEdit} style={{ height: 54, background: '#000', border: 'none', borderRadius: 8, fontWeight: 700 }}>
              保存并部署更新
            </Button>
          </div>
        </Form>
      </Drawer>
    </div>
  )
}
