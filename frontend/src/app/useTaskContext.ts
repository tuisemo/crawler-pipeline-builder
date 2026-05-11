import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import type { Task } from '../services/taskApi'
import { getTask, getTaskAsset } from '../services/taskApi'
import type { WorkflowGraph } from '../features/workflow/workflowContracts'
import type { WorkflowNode, WorkflowEdge } from '../features/workflow/workflowState'
import { graphToFlowState } from '../features/workflow/workflowState'

export interface TaskContext {
  taskId: number | null
  taskName: string | null
  task: Task | null
  loading: boolean
  error: string | null
  goBack: () => void
}

export function useTaskContext(): TaskContext {
  const params = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const taskId = params.taskId ? Number(params.taskId) : null

  const [task, setTask] = useState<Task | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!taskId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setTask(null)
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)

    getTask(taskId)
      .then((response) => {
        if (cancelled) return
        setTask(response.task)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load task')
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [taskId])

  const goBack = () => {
    if (taskId) {
      navigate(`/tasks/${taskId}`)
    } else {
      navigate('/tasks')
    }
  }

  return {
    taskId,
    taskName: task?.name ?? null,
    task,
    loading,
    error,
    goBack,
  }
}

export interface UseWorkflowAssetResult {
  loadAsset: (taskId: number) => Promise<{ nodes: WorkflowNode[]; edges: WorkflowEdge[] } | null>
}

export function useWorkflowAsset(): UseWorkflowAssetResult {
  const loadAsset = useCallback(async (id: number) => {
    const asset = await getTaskAsset(id, 'workflow_graph')
    if (!asset || !asset.content) return null
    try {
      const graph: WorkflowGraph = JSON.parse(asset.content)
      if (!graph.nodes || !graph.edges) return null
      const previousNodes: WorkflowNode[] = []
      return graphToFlowState(graph, previousNodes)
    } catch {
      return null
    }
  }, [])

  return { loadAsset }
}
