import { Button, Card, Segmented, Space, Spin, Tag, Tooltip, Typography } from 'antd'
import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  BarsOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  FileSearchOutlined,
  LayoutOutlined,
  RocketOutlined,
  SaveOutlined,
  NodeIndexOutlined,
  CloudUploadOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'
import type { ExtensionStatus } from '../../features/runtime/extensionBridge'
import type { ScriptGenerationMode } from '../../features/workflow/workflowContracts'

export type WorkbenchAction =
  | 'validate'
  | 'prompt'
  | 'compile-plan'
  | 'generate-skeleton'
  | 'generate-script'
  | 'auto-layout'

type WorkbenchToolbarProps = {
  runningAction: WorkbenchAction | null
  selectedNodeId: string
  workflowStats: {
    nodeCount: number
    edgeCount: number
    fieldCount: number
    hasPagination: boolean
  }
  onRunAction: (action: WorkbenchAction) => void
  generationMode: ScriptGenerationMode
  onGenerationModeChange: (mode: ScriptGenerationMode) => void
  extensionStatus: ExtensionStatus | null
  layout: {
    leftPanelOpen: boolean
    rightPanelOpen: boolean
    bottomDockOpen: boolean
    activeDockTab: string
    setLeftPanelOpen: (open: boolean) => void
    setRightPanelOpen: (open: boolean) => void
    openDockTab: (tab: 'results' | 'dsl') => void
  }
  taskName?: string | null
  onBack?: () => void
  onSaveToTask?: () => void
  saveToTaskLoading?: boolean
}

const actionConfig: Record<WorkbenchAction, { label: string; icon: ReactNode }> = {
  validate: { label: '校验 DSL', icon: <CheckCircleOutlined /> },
  prompt: { label: '预览 Prompt', icon: <FileSearchOutlined /> },
  'compile-plan': { label: '编排计划', icon: <AppstoreOutlined /> },
  'generate-skeleton': { label: '生成骨架', icon: <CodeOutlined /> },
  'generate-script': { label: '生成爬虫脚本', icon: <RocketOutlined /> },
  'auto-layout': { label: '优化布局', icon: <NodeIndexOutlined /> },
}

const groupedActions: Array<{ title: string; actions: WorkbenchAction[]; primary?: WorkbenchAction }> = [
  { title: '设计编排', actions: ['validate', 'prompt', 'compile-plan', 'auto-layout'] },
  { title: '执行脚本', actions: ['generate-skeleton', 'generate-script'], primary: 'generate-script' },
]

function renderExtensionTag(extensionStatus: ExtensionStatus | null) {
  if (!extensionStatus) {
    return <Tag color="default" className="toolbar-extension-pill">检测中…</Tag>
  }
  if (extensionStatus.installed && extensionStatus.ready) {
    return (
      <Tooltip title="Browser Bridge 已通过页面注入桥接接入当前工作台。">
        <Tag color="success" className="toolbar-extension-pill">
          <span className="pill-dot" />
          本地扩展已就绪
        </Tag>
      </Tooltip>
    )
  }
  return (
    <Tooltip title="未检测到工作台页面桥接。请确认已重新加载 Browser Bridge 扩展，并刷新当前工作台页面。">
      <Tag color="error" className="toolbar-extension-pill">
        未检测到扩展
      </Tag>
    </Tooltip>
  )
}

export function WorkbenchToolbar({
  runningAction,
  selectedNodeId,
  workflowStats,
  onRunAction,
  generationMode,
  onGenerationModeChange,
  extensionStatus,
  layout,
  taskName,
  onBack,
  onSaveToTask,
  saveToTaskLoading,
}: WorkbenchToolbarProps) {
  return (
    <Card className="ant-toolbar-card" styles={{ body: { padding: '8px 16px' } }} variant="outlined">
      <div className="toolbar-shell">
        {/* Header: Brand & Environment */}
        <div className="toolbar-header">
          <div className="toolbar-header-left">
            {onBack && (
              <>
                <Button
                  size="small"
                  icon={<ArrowLeftOutlined />}
                  onClick={onBack}
                  className="toolbar-back-btn"
                >
                  返回任务
                </Button>
                <div className="toolbar-separator" />
              </>
            )}
            {taskName && (
              <>
                <Typography.Text strong className="toolbar-task-name">
                  {taskName}
                </Typography.Text>
                <div className="toolbar-separator" />
              </>
            )}
            <div className="toolbar-logo-wrapper">
              <img src="/logo_128.webp" alt="Scraper Flow Studio" className="toolbar-logo-img" />
            </div>
            <div className="toolbar-brand-info">
              <Typography.Text strong className="toolbar-studio-title">
                Scraper Flow Studio
              </Typography.Text>
              <Typography.Text className="toolbar-studio-subtitle">
                Workflow Orchestration
              </Typography.Text>
            </div>
            <div className="toolbar-separator" />
            <Tag variant="filled" className="toolbar-active-context">
              <NodeIndexOutlined style={{ marginRight: 4 }} />
              {selectedNodeId || '未选择节点'}
            </Tag>
          </div>

          <div className="toolbar-header-right">
            {renderExtensionTag(extensionStatus)}
            <div className="toolbar-vertical-divider" />
            <div className="toolbar-view-controls">
              <div className="toolbar-control-item">
                <Typography.Text type="secondary" className="toolbar-mini-label">模式</Typography.Text>
                <Segmented
                  size="small"
                  value={generationMode}
                  onChange={(value) => onGenerationModeChange(value as ScriptGenerationMode)}
                  options={[
                    { label: 'Lite', value: 'lite' },
                    { label: 'Pro', value: 'pro' },
                  ]}
                />
              </div>
              <div className="toolbar-vertical-divider" />
              <Space.Compact>
                <Tooltip title="节点库">
                  <Button
                    className="toolbar-toggle-btn"
                    size="small"
                    type={layout.leftPanelOpen ? 'primary' : 'default'}
                    icon={<LayoutOutlined />}
                    onClick={() => layout.setLeftPanelOpen(!layout.leftPanelOpen)}
                  />
                </Tooltip>
                <Tooltip title="属性面板">
                  <Button
                    className="toolbar-toggle-btn"
                    size="small"
                    type={layout.rightPanelOpen ? 'primary' : 'default'}
                    icon={<AppstoreOutlined />}
                    onClick={() => layout.setRightPanelOpen(!layout.rightPanelOpen)}
                  />
                </Tooltip>
                <Tooltip title="执行结果">
                  <Button
                    className="toolbar-toggle-btn"
                    size="small"
                    type={layout.bottomDockOpen && layout.activeDockTab === 'results' ? 'primary' : 'default'}
                    icon={<BarsOutlined />}
                    onClick={() => layout.openDockTab('results')}
                  />
                </Tooltip>
                <Tooltip title="DSL 编辑器">
                  <Button
                    className="toolbar-toggle-btn"
                    size="small"
                    type={layout.bottomDockOpen && layout.activeDockTab === 'dsl' ? 'primary' : 'default'}
                    icon={<SaveOutlined />}
                    onClick={() => layout.openDockTab('dsl')}
                  />
                </Tooltip>
              </Space.Compact>
            </div>
          </div>
        </div>

        {/* Belt: Stats & Actions */}
        <div className="toolbar-belt">
          <div className="toolbar-belt-left">
            <div className="toolbar-stats-belt">
              <Tooltip title={`当前工作流包含 ${workflowStats.nodeCount} 个节点`}>
                <Tag className="toolbar-stat-pill">
                  <span className="stat-label">NODES</span>
                  <span className="stat-value">{workflowStats.nodeCount}</span>
                </Tag>
              </Tooltip>
              <Tooltip title={`当前工作流包含 ${workflowStats.edgeCount} 条连线`}>
                <Tag className="toolbar-stat-pill">
                  <span className="stat-label">EDGES</span>
                  <span className="stat-value">{workflowStats.edgeCount}</span>
                </Tag>
              </Tooltip>
              <Tooltip title={`已配置 ${workflowStats.fieldCount} 个抓取字段`}>
                <Tag className="toolbar-stat-pill">
                  <span className="stat-label">FIELDS</span>
                  <span className="stat-value">{workflowStats.fieldCount}</span>
                </Tag>
              </Tooltip>
              {workflowStats.hasPagination && (
                <Tag color="gold" className="toolbar-stat-pill toolbar-stat-pill-active">
                  PAGINATION ACTIVE
                </Tag>
              )}
            </div>
          </div>

          <div className="toolbar-belt-right">
            <div className="toolbar-actions-rail">
              {groupedActions.map((group) => (
                <div key={group.title} className="toolbar-action-group">
                  <div className="toolbar-action-group-inner">
                    <Typography.Text className="toolbar-group-tag">{group.title}</Typography.Text>
                    <Space size={6}>
                      {group.actions.filter(Boolean).map((action) => {
                        const cfg = actionConfig[action]
                        const isPrimary = group.primary === action
                        if (!cfg) return null;
                        return (
                          <Button
                            key={action}
                            id={`btn-action-${action}`}
                            className={`toolbar-action-btn ${isPrimary ? 'toolbar-action-btn-primary' : ''}`}
                            size="small"
                            type={isPrimary ? 'primary' : 'default'}
                            disabled={runningAction !== null}
                            onClick={() => onRunAction(action)}
                            icon={runningAction === action ? <Spin size="small" /> : cfg.icon}
                          >
                            {cfg.label}
                          </Button>
                        )
                      })}
                    </Space>
                  </div>
                </div>
              ))}
              {onSaveToTask && (
                <div className="toolbar-action-group">
                  <Typography.Text className="toolbar-group-tag">资产</Typography.Text>
                  <Button
                    size="small"
                    type="default"
                    icon={saveToTaskLoading ? <Spin size="small" /> : <CloudUploadOutlined />}
                    disabled={saveToTaskLoading || runningAction !== null}
                    onClick={onSaveToTask}
                    style={{ borderColor: 'rgba(37, 99, 235, 0.4)', color: '#2563eb' }}
                  >
                    保存到任务
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}
