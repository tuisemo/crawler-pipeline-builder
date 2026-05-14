// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { listTasks, createTask, getTask, updateTask, deleteTask, saveTaskAssets, getTaskAsset, UnauthorizedError, NotFoundError } from './taskApi'

const originalFetch = globalThis.fetch

describe('taskApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  // ── apiFetch header forwarding ──────────────────────────

  it('listTasks sends headers via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { items: [], total: 0 } }),
    } as Response)

    await listTasks()
    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
  })

  it('createTask sends headers via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'test', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' } } }),
    } as Response)

    await createTask({ name: 'test' })
    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
    expect(callArgs[1]?.method).toBe('POST')
  })

  it('getTask sends headers via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'test', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' }, assets: [] } }),
    } as Response)

    await getTask(1)
    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
  })

  it('updateTask sends headers via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'updated', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' } } }),
    } as Response)

    await updateTask(1, { name: 'updated' })
    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
    expect(callArgs[1]?.method).toBe('PUT')
  })

  it('deleteTask sends headers via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { task: { id: 1, name: 'test', description: null, target_url: null, status: 'draft', created_at: '', updated_at: '' } } }),
    } as Response)

    await deleteTask(1)
    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
    expect(callArgs[1]?.method).toBe('DELETE')
  })

  it('saveTaskAssets sends headers via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { saved_count: 1, assets: [] } }),
    } as Response)

    await saveTaskAssets(1, { schema: '{}' })
    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
    )
    expect(callArgs[1]?.method).toBe('POST')
  })

  it('getTaskAsset sends headers via apiFetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { asset_type: 'schema', version: 1, content: '{}', created_at: '' } }),
    } as Response)

    await getTaskAsset(1, 'schema')
    const callArgs = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[1]?.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' }),
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

  // ── 404 handling (request) ──────────────────────────────

  it('getTask throws NotFoundError on 404', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ success: false, error: 'Task not found' }),
    } as Response)

    await expect(getTask(999)).rejects.toThrow(NotFoundError)
  })

  it('NotFoundError has correct name and message', () => {
    const err = new NotFoundError()
    expect(err.name).toBe('NotFoundError')
    expect(err.message).toBe('Not found')

    const errCustom = new NotFoundError('Task not found')
    expect(errCustom.message).toBe('Task not found')
  })

  it('updateTask throws NotFoundError on 404', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ success: false, error: 'Task not found' }),
    } as Response)

    await expect(updateTask(999, { name: 'test' })).rejects.toThrow(NotFoundError)
  })

  it('deleteTask throws NotFoundError on 404', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ success: false, error: 'Task not found' }),
    } as Response)

    await expect(deleteTask(999)).rejects.toThrow(NotFoundError)
  })
})
