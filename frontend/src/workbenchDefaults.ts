import { MarkerType } from '@xyflow/react'
import type { PaletteItem } from './components/NodePalette'
import type { WorkflowNodeData, WorkflowNodeType } from './workflowContracts'
import type { WorkflowEdge, WorkflowNode } from './workflowState'

export type DockTabKey = 'results' | 'dsl'

export type WorkbenchLayoutState = {
  leftPanelOpen: boolean
  rightPanelOpen: boolean
  bottomDockOpen: boolean
  activeDockTab: DockTabKey
}

export const WORKBENCH_LAYOUT_STORAGE_KEY = 'crawler-workflow:workbench-layout:v1'

export const DEFAULT_WORKBENCH_LAYOUT: WorkbenchLayoutState = {
  leftPanelOpen: true,
  rightPanelOpen: true,
  bottomDockOpen: false,
  activeDockTab: 'results',
}

export function loadWorkbenchLayoutState(): WorkbenchLayoutState {
  if (typeof window === 'undefined') return DEFAULT_WORKBENCH_LAYOUT
  try {
    const raw = window.localStorage.getItem(WORKBENCH_LAYOUT_STORAGE_KEY)
    if (!raw) return DEFAULT_WORKBENCH_LAYOUT
    const parsed = JSON.parse(raw) as Partial<WorkbenchLayoutState>
    const activeDockTab: DockTabKey = parsed.activeDockTab === 'dsl' ? 'dsl' : 'results'
    return {
      leftPanelOpen: parsed.leftPanelOpen ?? DEFAULT_WORKBENCH_LAYOUT.leftPanelOpen,
      rightPanelOpen: parsed.rightPanelOpen ?? DEFAULT_WORKBENCH_LAYOUT.rightPanelOpen,
      bottomDockOpen: false,
      activeDockTab,
    }
  } catch {
    return DEFAULT_WORKBENCH_LAYOUT
  }
}

export function clampNumberInput(value: string, min: number, max: number, fallback: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(Math.max(parsed, min), max)
}

export function toPositiveLimit(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return null
  return Math.trunc(value)
}

export function createDefaultData(type: WorkflowNodeType): WorkflowNodeData {
  switch (type) {
    case 'open_page':
      return { label: '打开页面', url: '' }
    case 'select_list':
      return { label: '选择列表', item_selector: '' }
    case 'loop':
      return { label: '逐项循环', on_error: 'skip' }
    case 'extract_field':
      return { label: '字段抽取', fields: [{ name: 'title', selector: '', type: 'text' }] }
    case 'condition':
      return { label: '条件判断', condition: '', expression_mode: 'simple' }
    case 'paginate':
      return { label: '分页', pagination_selector: '', pagination_strategy: 'click_next' }
    case 'emit_record':
      return { label: '输出记录', output_mode: 'memory', write_mode: 'append', dedupe_keys: [], batch_size: 50 }
    case 'end':
      return { label: '结束' }
  }
}

export const paletteItems: PaletteItem[] = [
  { type: 'open_page', label: 'open_page', detail: '设置目标页面地址与访问边界' },
  { type: 'select_list', label: 'select_list', detail: '定位页面中重复的列表容器' },
  { type: 'loop', label: 'loop', detail: '逐项遍历上游列表，配置容错策略' },
  { type: 'extract_field', label: 'extract_field', detail: '从当前项中抽取结构化字段' },
  { type: 'condition', label: 'condition', detail: '按白名单条件切分执行路径（true/false）' },
  { type: 'paginate', label: 'paginate', detail: '处理翻页并重试下游采集链路' },
  { type: 'emit_record', label: 'emit_record', detail: '提交已抽取的记录结果' },
  { type: 'end', label: 'end', detail: '显式结束当前流程路径' },
]

export const initialNodes: WorkflowNode[] = [
  {
    id: 'open-page-1',
    type: 'open_page',
    position: { x: 60, y: 140 },
    data: { label: '打开页面', url: 'https://quotes.toscrape.com/' },
  },
  {
    id: 'select-list-1',
    type: 'select_list',
    position: { x: 330, y: 140 },
    data: { label: '选择列表', item_selector: '.quote' },
  },
  {
    id: 'extract-field-1',
    type: 'extract_field',
    position: { x: 600, y: 140 },
    data: { label: '字段抽取', fields: [{ name: 'text', selector: '.text', type: 'text' }] },
  },
]

export const initialEdges: WorkflowEdge[] = [
  {
    id: 'edge-open-select',
    source: 'open-page-1',
    target: 'select-list-1',
    markerEnd: { type: MarkerType.ArrowClosed },
  },
  {
    id: 'edge-select-extract',
    source: 'select-list-1',
    target: 'extract-field-1',
    markerEnd: { type: MarkerType.ArrowClosed },
  },
]
