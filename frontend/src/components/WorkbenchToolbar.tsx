import { Button, Card, Space, Spin, Tag, Tooltip, Typography } from 'antd'
import {
  AppstoreOutlined,
  BarsOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  CompassOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  LayoutOutlined,
  PlayCircleOutlined,
  RocketOutlined,
  SaveOutlined,
  NodeIndexOutlined
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export type WorkbenchAction =
  | 'validate'
  | 'prompt'
  | 'compile-plan'
  | 'generate-skeleton'
  | 'test-node'
  | 'test-subflow'
  | 'generate-script'
  | 'auto-layout'

type WorkbenchToolbarProps = {
  runningAction: WorkbenchAction | null
  selectedNodeId: string
  workflowStats: {
    nodeCount: number
    edgeCount: number
    fieldCount: number
    maxItems: number | null
    maxPages: number | null
    maxSteps: number | null
    hasPagination: boolean
  }
  onRunAction: (action: WorkbenchAction) => void
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
  'test-node': { label: '节点测试', icon: <ExperimentOutlined /> },
  'test-subflow': { label: '子流测试', icon: <PlayCircleOutlined /> },
  'generate-script': { label: '生成爬虫脚本', icon: <RocketOutlined /> },
  'auto-layout': { label: '优化布局', icon: <NodeIndexOutlined /> },
}

const groupedActions: Array<{ title: string; actions: WorkbenchAction[]; primary?: WorkbenchAction }> = [
  { title: '设计编排', actions: ['validate', 'prompt', 'compile-plan', 'auto-layout'] },
  { title: '执行脚本', actions: ['generate-skeleton', 'generate-script'], primary: 'generate-script' },
  { title: '运行验证', actions: ['test-node', 'test-subflow'] },
]

function formatLimit(value: number | null, suffix: string) {
  return value === null ? `未设${suffix}` : `${value.toLocaleString('zh-CN')}${suffix}`
}

export function WorkbenchToolbar({ runningAction, selectedNodeId, workflowStats, onRunAction, layout }: WorkbenchToolbarProps) {
  const executionSummary = [
    formatLimit(workflowStats.maxItems, '条'),
    formatLimit(workflowStats.maxPages, '页'),
    formatLimit(workflowStats.maxSteps, '步'),
  ].join(' / ')

  return (
    <Card className="ant-toolbar-card" styles={{ body: { padding: '8px 16px' } }} variant="outlined">
      <div className="toolbar-shell" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <div className="toolbar-brand" style={{ display: 'flex', alignItems: 'center' }}>
          <Space size={10}>
            <CompassOutlined style={{ color: 'var(--sd-color-primary-strong)', fontSize: 18 }} />
            <Typography.Text strong className="toolbar-brand-title" style={{ fontSize: 15, whiteSpace: 'nowrap' }}>
              Scraper Flow Studio
            </Typography.Text>
          </Space>
          <div className="toolbar-meta-chips" style={{ marginLeft: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Tag variant="filled" style={{ background: 'var(--sd-color-bg-softest)', color: 'var(--sd-color-primary-strong)', fontWeight: 700, borderRadius: 6, margin: 0 }}>
              选中: {selectedNodeId || '未选择'}
            </Tag>
            <Tag variant="borderless" color="blue" style={{ margin: 0 }}>节点 {workflowStats.nodeCount}</Tag>
            <Tag variant="borderless" color="cyan" style={{ margin: 0 }}>连线 {workflowStats.edgeCount}</Tag>
            <Tag variant="borderless" color="purple" style={{ margin: 0 }}>字段 {workflowStats.fieldCount}</Tag>
          </div>
          <div style={{ marginLeft: 24 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              执行边界: <Typography.Text strong style={{ color: 'var(--sd-color-text)', fontSize: 12 }}>{executionSummary}</Typography.Text>
            </Typography.Text>
          </div>
        </div>

        <div className="workspace-switcher" style={{ display: 'flex', alignItems: 'center' }}>
          <Space.Compact>
            <Tooltip title="显示或隐藏左侧节点库">
              <Button
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

        <div className="toolbar-actions" style={{ display: 'flex', gap: 16 }}>
          {groupedActions.map((group) => (
            <div key={group.title} className="toolbar-action-group" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <Typography.Text type="secondary" style={{ fontSize: 10, textTransform: 'uppercase', fontWeight: 800 }}>
                {group.title}
              </Typography.Text>
              <Space size={6}>
                {group.actions.map((action) => {
                  const cfg = actionConfig[action]
                  return (
                    <Button
                      key={action}
                      size="small"
                      type={group.primary === action ? 'primary' : 'default'}
                      disabled={runningAction !== null || (action === 'test-node' && !selectedNodeId)}
                      onClick={() => onRunAction(action)}
                      icon={runningAction === action ? <Spin size="small" /> : cfg.icon}
                      style={{ borderRadius: 6 }}
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
