// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { listTasks, createTask, getTask, updateTask, deleteTask, saveTaskAssets, getTaskAsset, UnauthorizedError } from './taskApi'

const originalFetch = globalThis.fetch

describe('taskApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  // ── credentials: 'include' ──────────────────────────────

  it('listTasks includes credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { items: [], total: 0 } }),
    } as Response)

    await listTasks()
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('createTask includes credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'test', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' } } }),
    } as Response)

    await createTask({ name: 'test' })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include', method: 'POST' }),
    )
  })

  it('getTask includes credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'test', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' }, assets: [] } }),
    } as Response)

    await getTask(1)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('updateTask includes credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'updated', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' } } }),
    } as Response)

    await updateTask(1, { name: 'updated' })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include', method: 'PUT' }),
    )
  })

  it('deleteTask includes credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'test', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' } } }),
    } as Response)

    await deleteTask(1)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include', method: 'DELETE' }),
    )
  })

  it('saveTaskAssets includes credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { saved_count: 1, assets: [] } }),
    } as Response)

    await saveTaskAssets(1, { schema: '{}' })
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include', method: 'POST' }),
    )
  })

  it('getTaskAsset includes credentials: include', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { asset_type: 'schema', version: 1, content: '{}', created_at: '' } }),
    } as Response)

    await getTaskAsset(1, 'schema')
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  // ── 401 handling ────────────────────────────────────────

  it('listTasks throws UnauthorizedError on 401', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(listTasks()).rejects.toThrow(UnauthorizedError)
  })

  it('createTask throws UnauthorizedError on 401', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(createTask({ name: 'test' })).rejects.toThrow(UnauthorizedError)
  })

  it('getTask throws UnauthorizedError on 401', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(getTask(1)).rejects.toThrow(UnauthorizedError)
  })

  // ── 404 handling (requestOrNull) ────────────────────────

  it('getTaskAsset returns null on 404', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ success: false, error: 'Not found' }),
    } as Response)

    const result = await getTaskAsset(1, 'schema')
    expect(result).toBeNull()
  })

  it('getTaskAsset throws UnauthorizedError on 401', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: 'Not authenticated' }),
    } as Response)

    await expect(getTaskAsset(1, 'schema')).rejects.toThrow(UnauthorizedError)
  })
})
