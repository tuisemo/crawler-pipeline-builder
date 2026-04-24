export type WorkflowNodeType =
  | 'open_page'
  | 'select_list'
  | 'loop'
  | 'extract_field'
  | 'condition'
  | 'paginate'
  | 'emit_record'
  | 'end'

export type ExtractionField = {
  name?: string
  field_name?: string
  selector?: string
  css?: string
  type?: string
  extraction_type?: string
  sample_value?: string
  normalized_sample?: string
  clean_data_type?: string
  [key: string]: unknown
}

export type WorkflowNodeData = {
  label?: string
  // open_page
  url?: string
  max_pages?: number
  max_steps?: number
  // select_list
  item_selector?: string
  max_items?: number
  // loop
  on_error?: 'skip' | 'stop'
  // extract_field
  fields?: ExtractionField[]
  html_fragment?: string
  // condition
  condition?: string
  expression_mode?: 'simple' | 'advanced'
  // paginate
  pagination_selector?: string
  pagination_strategy?: string
  // emit_record / end
  [key: string]: unknown
}

export type WorkflowBranch = 'true' | 'false' | 'default' | boolean

export type CanonicalWorkflowEdge = {
  id: string
  source: string
  target: string
  branch?: WorkflowBranch
  label?: string
  order?: number
}
export type CanonicalWorkflowNode = { id: string; type: WorkflowNodeType; data: WorkflowNodeData }

export type WorkflowGraph = {
  nodes: CanonicalWorkflowNode[]
  edges: CanonicalWorkflowEdge[]
}
