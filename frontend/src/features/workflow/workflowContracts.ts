export type WorkflowNodeType =
  | 'open_page'
  | 'select_list'
  | 'loop'
  | 'extract_field'
  | 'condition'
  | 'paginate'
  | 'emit_record'
  | 'end'

export type ScriptGenerationMode = 'lite' | 'pro'

export type AssistApplyMode = 'current-only' | 'related-nodes'

export type ExtractionField = {
  name?: string
  selector?: string
  type?: string
  /** @deprecated Use 'name' instead */
  field_name?: string
  /** @deprecated Use 'selector' instead */
  css?: string
  /** @deprecated No longer used in stateless mode */
  extraction_type?: string
  [key: string]: unknown
}

export type WorkflowNodeData = {
  label?: string
  // open_page
  url?: string
  // select_list
  item_selector?: string
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
  // emit_record
  output_mode?: 'memory' | 'json_file' | 'sqlite' | string
  json_file_path?: string
  sqlite_path?: string
  sqlite_table?: string
  write_mode?: 'append' | 'upsert' | string
  dedupe_keys?: string[]
  batch_size?: number
  // end
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
