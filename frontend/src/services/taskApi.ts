import type { ApiEnvelope } from './workflowApi'

export interface Task {
  id: number
  name: string
  description: string | null
  target_url: string | null
  status: 'draft' | 'active' | 'archived'
  created_at: string
  updated_at: string
}

export interface TaskAsset {
  asset_type: string
  version: number
  created_at: string
}

export interface TaskDetailResponse {
  task: Task
  assets: TaskAsset[]
}

export interface TaskListResponse {
  items: Task[]
  total: number
  page: number
  page_size: number
}

export interface CreateTaskRequest {
  name: string
  description?: string
  target_url?: string
}

export interface UpdateTaskRequest {
  name?: string
  description?: string
  target_url?: string
  status?: 'draft' | 'active' | 'archived'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isApiEnvelope(value: unknown): value is ApiEnvelope {
  if (!isRecord(value)) return false
  return typeof value.success === 'boolean' && Object.prototype.hasOwnProperty.call(value, 'data')
}

async function parseEnvelope(response: Response): Promise<{ data: Record<string, unknown>; envelope: ApiEnvelope }> {
  const raw: unknown = await response.json().catch(() => ({}))
  const envelope: ApiEnvelope = isApiEnvelope(raw)
    ? raw
    : { success: false, error: 'Invalid response', data: {} }
  const data = envelope.success && isRecord(envelope.data) ? envelope.data : {}
  return { data, envelope }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const { data, envelope } = await parseEnvelope(response)
  if (!response.ok || !envelope.success) {
    throw new Error(envelope.error || 'Request failed')
  }
  return data as T
}

export async function listTasks(params?: { page?: number; page_size?: number }): Promise<TaskListResponse> {
  const query = new URLSearchParams()
  if (params?.page) query.set('page', String(params.page))
  if (params?.page_size) query.set('page_size', String(params.page_size))
  const queryStr = query.toString()
  return request<TaskListResponse>(`/api/tasks${queryStr ? `?${queryStr}` : ''}`)
}

export async function createTask(body: CreateTaskRequest): Promise<{ task: Task }> {
  return request<{ task: Task }>('/api/tasks', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateTask(taskId: number, body: UpdateTaskRequest): Promise<{ task: Task }> {
  return request<{ task: Task }>(`/api/tasks/${taskId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export async function deleteTask(taskId: number): Promise<{ task: Task }> {
  return request<{ task: Task }>(`/api/tasks/${taskId}`, {
    method: 'DELETE',
  })
}

export async function getTask(taskId: number): Promise<TaskDetailResponse> {
  return request<TaskDetailResponse>(`/api/tasks/${taskId}`)
}
