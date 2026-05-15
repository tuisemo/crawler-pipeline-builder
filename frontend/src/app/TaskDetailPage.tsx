import React from 'react'
import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Button, Typography, Space, Tag, Drawer, Form, Input, message, Empty,
  Breadcrumb, Result, Tooltip, Modal, Badge, Divider,
} from 'antd'
import {
  EditOutlined, EnterOutlined, CheckCircleOutlined, CodeOutlined,
  CopyOutlined, ExportOutlined, ThunderboltFilled, DatabaseOutlined,
  DeploymentUnitOutlined, BranchesOutlined, RetweetOutlined, RightCircleOutlined,
} from '@ant-design/icons'
import type { AssetMeta } from '../services/taskApi'
import {
  getTask, updateTask, createTask, saveTaskAssets, getTaskAsset, type Task,
  UnauthorizedError, NotFoundError,
} from '../services/taskApi'
import { AssetViewerDrawer } from './components/AssetViewerDrawer'
import './TaskDetailPage.css'

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

const assetTypeIcon: Record<string, React.ReactNode> = {
  workflow_graph: <BranchesOutlined />,
  compile_plan: <CodeOutlined />,
  list_script: <CodeOutlined />,
  prompt: <CodeOutlined />,
  detail_batch_config: <DatabaseOutlined />,
  detail_batch_script: <CodeOutlined />,
}

function getTargetHostLabel(targetUrl: string | null): string {
  if (!targetUrl) return '本地'
  try { return new URL(targetUrl).hostname || targetUrl }
  catch { return targetUrl }
}

// Parse workflow_graph to extract feature insights
type WorkflowInsight = {
  nodeCount: number
  fieldCount: number
  hasPaginate: boolean
  hasLoop: boolean
  hasCondition: boolean
  outputMode: string | null
}

function parseWorkflowInsights(json: string | null): WorkflowInsight | null {
  if (!json) return null
  try {
    const graph = JSON.parse(json) as { nodes?: { type: string; data: Record<string, unknown> }[] }
    if (!Array.isArray(graph.nodes)) return null
    const nodes = graph.nodes
    const fieldCount = nodes
      .filter((n) => n.type === 'extract_field')
      .reduce((sum, n) => sum + (Array.isArray(n.data?.fields) ? (n.data.fields as unknown[]).length : 0), 0)
    const emitNode = nodes.find((n) => n.type === 'emit_record')
    return {
      nodeCount: nodes.length,
      fieldCount,
      hasPaginate: nodes.some((n) => n.type === 'paginate'),
      hasLoop: nodes.some((n) => n.type === 'loop'),
      hasCondition: nodes.some((n) => n.type === 'condition'),
      outputMode: emitNode ? String(emitNode.data?.output_mode || 'memory') : null,
    }
  } catch { return null }
}

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const [task, setTask] = useState<Task | null>(null)
  const [assets, setAssets] = useState<AssetMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [notFound, setNotFound] = useState(false)

  // Workflow snapshot
  const [workflowJson, setWorkflowJson] = useState<string | null>(null)

  // Edit drawer
  const [editDrawerOpen, setEditDrawerOpen] = useState(false)
  const [editForm] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)

  // Asset viewer
  const [viewerAssetType, setViewerAssetType] = useState<string>('')
  const [viewerLatestVersion, setViewerLatestVersion] = useState<number>(1)
  const [assetViewerOpen, setAssetViewerOpen] = useState(false)

  // Clone
  const [cloning, setCloning] = useState(false)

  // Export
  const [exporting, setExporting] = useState(false)

  const id = taskId ? parseInt(taskId, 10) : NaN

  useEffect(() => {
    let cancelled = false
    async function fetchTask() {
      if (isNaN(id)) { setNotFound(true); return }
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
          if (err instanceof NotFoundError) setNotFound(true)
          else if (err instanceof UnauthorizedError) message.error('登录已过期，请重新登录')
          else message.error('加载任务详情失败')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchTask()
    return () => { cancelled = true }
  }, [id])

  // Load workflow_graph for snapshot and insights
  useEffect(() => {
    if (isNaN(id)) return
    getTaskAsset(id, 'workflow_graph').then((res) => {
      if (res?.content) setWorkflowJson(res.content)
    }).catch(() => { /* silent */ })
  }, [id])

  const insights = useMemo(() => parseWorkflowInsights(workflowJson), [workflowJson])

  // De-duplicate assets: keep only the latest version per asset_type
  const latestAssets = useMemo(() => {
    const map = new Map<string, AssetMeta>()
    for (const asset of assets) {
      const existing = map.get(asset.asset_type)
      if (!existing || asset.version > existing.version) map.set(asset.asset_type, asset)
    }
    return Array.from(map.values())
  }, [assets])

  async function handleEdit() {
    if (!task) return
    let values: { name?: string; description?: string; target_url?: string }
    try { values = await editForm.validateFields() } catch { return }
    setSubmitting(true)
    try {
      const updated = await updateTask(task.id, values)
      setTask(updated.task)
      setEditDrawerOpen(false)
      message.success('任务更新成功')
    } catch { message.error('更新任务失败') }
    finally { setSubmitting(false) }
  }

  function openEditDrawer() {
    if (!task) return
    editForm.setFieldsValue({ name: task.name, description: task.description, target_url: task.target_url })
    setEditDrawerOpen(true)
  }

  function openAssetViewer(assetType: string, latestVersion: number) {
    setViewerAssetType(assetType)
    setViewerLatestVersion(latestVersion)
    setAssetViewerOpen(true)
  }

  async function handleCloneTask() {
    if (!task) return
    Modal.confirm({
      title: '克隆任务',
      content: `将以"${task.name}_副本"为名称创建新任务，并复制当前工作流图结构。`,
      okText: '确认克隆',
      cancelText: '取消',
      okButtonProps: { style: { background: '#000', border: 'none' } },
      onOk: async () => {
        setCloning(true)
        try {
          const res = await createTask({
            name: `${task.name}_副本`,
            description: task.description ?? undefined,
            target_url: task.target_url ?? undefined,
          })
          if (workflowJson) {
            await saveTaskAssets(res.task.id, { workflow_graph: workflowJson })
          }
          message.success('任务克隆成功')
          navigate(`/tasks/${res.task.id}`)
        } catch { message.error('克隆任务失败') }
        finally { setCloning(false) }
      },
    })
  }

  async function handleExportProject() {
    if (!task) return
    setExporting(true)
    try {
      const JSZip = (await import('jszip')).default
      const zip = new JSZip()
      const assetTypes = ['workflow_graph', 'list_script', 'prompt', 'detail_batch_config', 'detail_batch_script', 'compile_plan']
      const extMap: Record<string, string> = {
        workflow_graph: 'json', compile_plan: 'json', detail_batch_config: 'json',
        list_script: 'py', detail_batch_script: 'py', prompt: 'md',
      }
      await Promise.all(assetTypes.map(async (type) => {
        try {
          const res = await getTaskAsset(id, type)
          if (res?.content) zip.file(`${type}.${extMap[type] || 'txt'}`, res.content)
        } catch { /* skip missing */ }
      }))
      const blob = await zip.generateAsync({ type: 'blob' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `task_${task.id}_${task.name.replace(/\s+/g, '_')}.zip`
      link.click()
      URL.revokeObjectURL(url)
      message.success('工程包导出成功')
    } catch { message.error('导出失败，请重试') }
    finally { setExporting(false) }
  }

  if (notFound) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '80vh' }}>
        <Result status="404" title="任务不存在"
          subTitle="该任务可能已被删除，或者您没有访问权限。"
          extra={<Button type="primary" onClick={() => navigate('/tasks')} style={{ background: '#000', border: 'none', borderRadius: 8 }}>返回任务列表</Button>}
        />
      </div>
    )
  }

  if (loading && !task) {
    return (
      <div style={{ padding: 100, textAlign: 'center' }}>
        <div className="mono" style={{ color: 'var(--sd-color-primary)', fontSize: 14 }}>同步工作空间资源...</div>
      </div>
    )
  }

  return (
    <div className="tech-workspace">
      {/* ── Left Sidebar ── */}
      <div className="tech-sidebar">
        <Breadcrumb
          items={[
            { title: <a onClick={() => navigate('/tasks')} style={{ color: '#999' }}>任务列表</a> },
            { title: <span className="mono" style={{ color: '#000' }}>#{task?.id.toString().padStart(3, '0')}</span> },
          ]}
          style={{ marginBottom: 32 }}
        />

        {/* Title & Status */}
        <div style={{ marginBottom: 24 }}>
          <div className="mono" style={{ color: '#bbb', fontSize: 11, letterSpacing: '0.1em', marginBottom: 10 }}>任务标识符</div>
          <Title level={3} style={{ margin: 0, fontSize: 22, letterSpacing: '-0.02em', lineHeight: 1.3 }}>{task?.name}</Title>
          <Tag color={task?.status === 'active' ? 'success' : 'default'} style={{ marginTop: 10, borderRadius: 4 }}>
            {task?.status === 'active' ? '● 正在运行' : '○ 待处理'}
          </Tag>
        </div>

        <Divider style={{ margin: '16px 0' }} />

        {/* Metadata */}
        <div style={{ marginBottom: 20 }}>
          <div className="mono" style={{ color: '#bbb', fontSize: 11, letterSpacing: '0.1em', marginBottom: 14 }}>系统元数据</div>
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            {[
              ['创建时间', task ? new Date(task.created_at).toLocaleDateString('zh-CN') : '--'],
              ['最后更新', task ? new Date(task.updated_at).toLocaleDateString('zh-CN') : '--'],
              ['目标域名', getTargetHostLabel(task?.target_url ?? null)],
            ].map(([label, value]) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px dashed #f0f0f0', paddingBottom: 8 }}>
                <span style={{ color: '#999', fontSize: 12 }}>{label}</span>
                <span className="mono" style={{ fontSize: 12, color: '#333' }}>{value}</span>
              </div>
            ))}
          </Space>
        </div>

        {/* Workflow Insights */}
        {insights && (
          <div style={{ marginBottom: 20 }}>
            <Divider style={{ margin: '16px 0' }} />
            <div className="mono" style={{ color: '#bbb', fontSize: 11, letterSpacing: '0.1em', marginBottom: 14 }}>工作流特征</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              <Tag icon={<DeploymentUnitOutlined />} style={{ border: '1px solid #e2e8f0', borderRadius: 6 }}>
                {insights.nodeCount} 节点
              </Tag>
              {insights.fieldCount > 0 && (
                <Tag icon={<DatabaseOutlined />} style={{ border: '1px solid #e2e8f0', borderRadius: 6 }}>
                  {insights.fieldCount} 字段
                </Tag>
              )}
              {insights.hasPaginate && (
                <Tag icon={<RightCircleOutlined />} color="cyan" style={{ borderRadius: 6, border: 'none' }}>
                  自动翻页
                </Tag>
              )}
              {insights.hasLoop && (
                <Tag icon={<RetweetOutlined />} color="purple" style={{ borderRadius: 6, border: 'none' }}>
                  循环处理
                </Tag>
              )}
              {insights.hasCondition && (
                <Tag icon={<BranchesOutlined />} color="orange" style={{ borderRadius: 6, border: 'none' }}>
                  条件分支
                </Tag>
              )}
              {insights.outputMode && (
                <Tag icon={<ThunderboltFilled />} color="green" style={{ borderRadius: 6, border: 'none' }}>
                  {insights.outputMode}
                </Tag>
              )}
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Button block icon={<EditOutlined />} onClick={openEditDrawer} style={{ height: 38, borderRadius: 8 }}>
            修改任务配置
          </Button>
          <Button block icon={<CopyOutlined />} onClick={handleCloneTask} loading={cloning} style={{ height: 38, borderRadius: 8 }}>
            克隆任务
          </Button>
          <Tooltip title="将工作流图、脚本和提示词打包下载">
            <Button block icon={<ExportOutlined />} onClick={handleExportProject} loading={exporting} style={{ height: 38, borderRadius: 8 }}>
              导出工程包
            </Button>
          </Tooltip>
          <Button
            block type="primary" icon={<EnterOutlined />}
            onClick={() => navigate(`/tasks/${taskId}/workbench`)}
            style={{ height: 40, borderRadius: 8, background: '#000', border: 'none', marginTop: 4 }}
          >
            进入流程工作站
          </Button>
        </div>
      </div>

      {/* ── Main Content ── */}
      <div className="tech-main">
        <div style={{ maxWidth: 960, margin: '0 auto' }}>

          {/* Description */}
          <section style={{ marginBottom: 40 }}>
            <div className="mono" style={{ color: '#bbb', fontSize: 11, marginBottom: 16, letterSpacing: '0.1em' }}>
              业务描述 / DESCRIPTION
            </div>
            <div className="task-description-block">
              {task?.description || '暂无该任务的详细业务描述。您可以通过"修改任务配置"添加相关背景。'}
            </div>
          </section>

          {/* Assets */}
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, paddingBottom: 14, borderBottom: '2px solid #000' }}>
              <div className="mono" style={{ fontSize: 14 }}>
                存储资产库 <span style={{ color: '#ccc', fontWeight: 400 }}>({latestAssets.length} 类型)</span>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>点击卡片预览内容与历史版本</Text>
            </div>

            {latestAssets.length === 0 ? (
              <div style={{ padding: '80px 0', textAlign: 'center', background: '#fafafa', borderRadius: 16, border: '1px dashed #ddd' }}>
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span style={{ color: '#999' }}>暂未检测到已编译资产</span>} />
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {latestAssets.map((asset) => (
                  <div
                    key={asset.asset_type}
                    className="tech-card-horizontal asset-card-clickable"
                    onClick={() => openAssetViewer(asset.asset_type, asset.version)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                      <div className="asset-icon-wrapper">
                        <CheckCircleOutlined style={{ color: 'var(--sd-color-success)', fontSize: 18 }} />
                      </div>
                      <div>
                        <div style={{ fontSize: 15, color: '#000', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
                          {assetTypeLabel[asset.asset_type] || asset.asset_type}
                          <span style={{ color: '#ccc' }}>{assetTypeIcon[asset.asset_type]}</span>
                        </div>
                        <div className="mono" style={{ fontSize: 11, color: '#bbb', marginTop: 2 }}>
                          {asset.asset_type.toUpperCase()}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                      <Badge
                        count={`REV_${String(asset.version).padStart(2, '0')}`}
                        style={{ background: '#000', fontFamily: 'var(--sd-font-mono)', fontSize: 11, borderRadius: 6, padding: '0 8px' }}
                      />
                      <div style={{ textAlign: 'right' }}>
                        <div className="mono" style={{ fontSize: 11, color: '#ccc' }}>
                          {new Date(asset.created_at).toLocaleDateString('zh-CN')}
                        </div>
                        <div style={{ fontSize: 11, color: '#bbb', marginTop: 2 }}>点击查看版本历史 →</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      {/* ── Asset Viewer Drawer ── */}
      <AssetViewerDrawer
        open={assetViewerOpen}
        taskId={id}
        assetType={viewerAssetType}
        latestVersion={viewerLatestVersion}
        onClose={() => setAssetViewerOpen(false)}
        onRollbackSuccess={() => {
          setAssetViewerOpen(false)
          getTask(id).then((d) => { setTask(d.task); setAssets(d.assets) }).catch(() => { })
        }}
      />

      {/* ── Edit Configuration Drawer ── */}
      <Drawer
        title={<span className="mono">配置更新 / EDIT_CONFIG</span>}
        placement="right"
        size="large"
        open={editDrawerOpen}
        onClose={() => setEditDrawerOpen(false)}
        styles={{ body: { padding: '32px' } }}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label={<span className="mono" style={{ fontSize: 12 }}>任务识别名</span>}
            rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0', fontSize: 16 }} />
          </Form.Item>
          <Form.Item name="description" label={<span className="mono" style={{ fontSize: 12 }}>业务背景</span>}>
            <TextArea rows={5} bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
          <Form.Item name="target_url" label={<span className="mono" style={{ fontSize: 12 }}>目标起始地址</span>}>
            <Input bordered={false} style={{ borderBottom: '1px solid #eee', borderRadius: 0, padding: '12px 0' }} />
          </Form.Item>
          <div style={{ marginTop: 40 }}>
            <Button type="primary" block size="large" loading={submitting} onClick={handleEdit}
              style={{ height: 54, background: '#000', border: 'none', borderRadius: 8 }}>
              保存并更新
            </Button>
          </div>
        </Form>
      </Drawer>
    </div>
  )
}
