import { apiFetch, UnauthorizedError } from './apiClient'
import type { ApiEnvelope } from './workflowApi'

export type TaskStatus = 'draft' | 'active' | 'archived'

export interface Task {
  id: number
  name: string
  description: string | null
  target_url: string | null
  status: TaskStatus
  created_at: string
  updated_at: string
}

export interface AssetMeta {
  asset_type: string
  version: number
  created_at: string
}

export interface AssetItem {
  asset_type: string
  version: number
  content: string
  created_at: string
}

export interface TaskListResponse {
  items: Task[]
  total: number
}

export interface TaskDetailResponse {
  task: Task
  assets: AssetMeta[]
}

export interface SaveAssetsResponse {
  saved_count: number
  assets: AssetMeta[]
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

// Re-export UnauthorizedError so callers can catch it specifically
export { UnauthorizedError }

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await apiFetch(path, options)
  const { data, envelope } = await parseEnvelope(response)
  if (!response.ok || !envelope.success) {
    throw new Error(envelope.error || 'Request failed')
  }
  return data as T
}

async function requestOrNull<T>(path: string, options?: RequestInit): Promise<T | null> {
  const response = await apiFetch(path, options)
  if (response.status === 404) {
    return null
  }
  const { data, envelope } = await parseEnvelope(response)
  if (!response.ok || !envelope.success) {
    throw new Error(envelope.error || 'Request failed')
  }
  return data as T
}

export async function listTasks(
  page: number = 1,
  pageSize: number = 20,
  status?: TaskStatus
): Promise<TaskListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (status) params.set('status', status)
  return request<TaskListResponse>(`/api/tasks?${params.toString()}`)
}

export async function createTask(data: { name: string; description?: string; target_url?: string }): Promise<{ task: Task }> {
  return request<{ task: Task }>('/api/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTask(taskId: number): Promise<TaskDetailResponse> {
  return request<TaskDetailResponse>(`/api/tasks/${taskId}`)
}

export async function updateTask(
  taskId: number,
  data: { name?: string; description?: string; target_url?: string; status?: TaskStatus }
): Promise<{ task: Task }> {
  return request<{ task: Task }>(`/api/tasks/${taskId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteTask(taskId: number): Promise<{ task: Task }> {
  return request<{ task: Task }>(`/api/tasks/${taskId}`, {
    method: 'DELETE',
  })
}

export async function saveTaskAssets(
  taskId: number,
  assets: Record<string, string>
): Promise<SaveAssetsResponse> {
  return request<SaveAssetsResponse>(`/api/tasks/${taskId}/assets`, {
    method: 'POST',
    body: JSON.stringify({ assets }),
  })
}

export async function getTaskAsset(taskId: number, assetType: string): Promise<AssetItem | null> {
  return requestOrNull<AssetItem>(`/api/tasks/${taskId}/assets/${assetType}`)
}
