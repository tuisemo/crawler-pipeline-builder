import { Button, Card, Segmented, Space, Spin, Tag, Tooltip, Typography } from 'antd'
import {
  AppstoreOutlined,
  BarsOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  CompassOutlined,
  FileSearchOutlined,
  LayoutOutlined,
  RocketOutlined,
  SaveOutlined,
  NodeIndexOutlined,
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
    return <Tag color="default" className="toolbar-chip">检测中…</Tag>
  }
  if (extensionStatus.installed && extensionStatus.ready) {
    return (
      <Tooltip title="Browser Bridge 已通过页面注入桥接接入当前工作台。">
        <Tag color="success" className="toolbar-chip">
          已就绪（本地扩展加速中）
        </Tag>
      </Tooltip>
    )
  }
  return (
    <Tooltip title="未检测到工作台页面桥接。请确认已重新加载 Browser Bridge 扩展，并刷新当前工作台页面。">
      <Tag color="error" className="toolbar-chip">
        未安装扩展
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
}: WorkbenchToolbarProps) {
  return (
    <Card className="ant-toolbar-card" styles={{ body: { padding: '10px 14px' } }} variant="outlined">
      <div className="toolbar-shell">
        <div className="toolbar-top">
          <div className="toolbar-brand">
            <div className="toolbar-brand-row">
              <div className="toolbar-brand-badge">
                <CompassOutlined />
              </div>
              <div className="toolbar-brand-copy">
                <Typography.Text className="toolbar-eyebrow">
                  Workflow Orchestration Workbench
                </Typography.Text>
                <Typography.Text strong className="toolbar-brand-title">
                  Scraper Flow Studio
                </Typography.Text>
              </div>
              <Tag variant="filled" className="toolbar-chip toolbar-chip-active toolbar-chip-inline">
                {selectedNodeId || '未选择节点'}
              </Tag>
            </div>
            <div className="toolbar-summary-line">
              <div className="toolbar-meta-chips">
                <Tag color="blue" className="toolbar-chip">节点 {workflowStats.nodeCount}</Tag>
                <Tag color="cyan" className="toolbar-chip">连线 {workflowStats.edgeCount}</Tag>
                <Tag color="purple" className="toolbar-chip">字段 {workflowStats.fieldCount}</Tag>
                {workflowStats.hasPagination ? <Tag color="gold" className="toolbar-chip">分页</Tag> : null}
                {renderExtensionTag(extensionStatus)}
              </div>
              <Typography.Text type="secondary" className="toolbar-summary-label">
                分页行为
              </Typography.Text>
              <Typography.Text className="toolbar-summary-value">
                {workflowStats.hasPagination ? '按站点翻页条件自动结束' : '未启用分页'}
              </Typography.Text>
            </div>
          </div>

          <div className="toolbar-inline-rail">
            <div className="toolbar-control-row">
              <Typography.Text type="secondary" className="toolbar-group-title">
                模式
              </Typography.Text>
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

            <div className="toolbar-control-row">
              <Typography.Text type="secondary" className="toolbar-group-title">
                工作区
              </Typography.Text>
              <Space.Compact>
                <Tooltip title="显示或隐藏左侧节点库">
                  <Button
                    className="toolbar-action-btn toolbar-toggle-btn"
                    size="small"
                    type={layout.leftPanelOpen ? 'primary' : 'default'}
                    icon={<LayoutOutlined />}
                    onClick={() => layout.setLeftPanelOpen(!layout.leftPanelOpen)}
                  >
                    节点库
                  </Button>
                </Tooltip>
                <Tooltip title="显示或隐藏右侧属性配置">
                  <Button
                    className="toolbar-action-btn toolbar-toggle-btn"
                    size="small"
                    type={layout.rightPanelOpen ? 'primary' : 'default'}
                    icon={<AppstoreOutlined />}
                    onClick={() => layout.setRightPanelOpen(!layout.rightPanelOpen)}
                  >
                    属性
                  </Button>
                </Tooltip>
                <Tooltip title="打开执行结果工作区">
                  <Button
                    className="toolbar-action-btn toolbar-toggle-btn"
                    size="small"
                    type={layout.bottomDockOpen && layout.activeDockTab === 'results' ? 'primary' : 'default'}
                    icon={<BarsOutlined />}
                    onClick={() => layout.openDockTab('results')}
                  >
                    结果
                  </Button>
                </Tooltip>
                <Tooltip title="打开 DSL 编辑器">
                  <Button
                    className="toolbar-action-btn toolbar-toggle-btn"
                    size="small"
                    type={layout.bottomDockOpen && layout.activeDockTab === 'dsl' ? 'primary' : 'default'}
                    icon={<SaveOutlined />}
                    onClick={() => layout.openDockTab('dsl')}
                  >
                    DSL
                  </Button>
                </Tooltip>
              </Space.Compact>
            </div>
          </div>
        </div>

        <div className="toolbar-actions toolbar-actions-compact">
          {groupedActions.map((group) => (
            <div key={group.title} className="toolbar-action-group toolbar-action-group-compact">
              <Typography.Text type="secondary" className="toolbar-group-title">
                {group.title}
              </Typography.Text>
              <Space size={8} wrap>
                {group.actions.map((action) => {
                  const cfg = actionConfig[action]
                  return (
                    <Button
                      key={action}
                      className={group.primary === action ? 'toolbar-action-btn toolbar-action-btn-primary' : 'toolbar-action-btn'}
                      size="small"
                      type={group.primary === action ? 'primary' : 'default'}
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
          ))}
        </div>
      </div>
    </Card>
  )
}
