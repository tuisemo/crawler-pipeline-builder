"""Orchestration helpers for workflow executor subflow execution."""

from __future__ import annotations

from .workflow_executor_helpers import build_partial_subflow_response
from .workflow_executor_traversal import enqueue_successors, pop_next_subflow_node
from .workflow_schemas import LogLevel


def _normalize_branch_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false", "default"}:
            return lowered
    return None


def _select_condition_successor(graph, node_id, successors, condition_result):
    """Select a condition branch target using edge metadata first.

    Branch matching priority:
    1) edge.branch == true/false
    2) edge.branch == default
    3) fallback to legacy order-based behavior
    """
    target_branch = "true" if condition_result else "false"
    condition_edges = [
        edge for edge in graph.edges
        if edge.source == node_id and edge.target in successors
    ]
    if condition_edges:
        explicit = [
            edge for edge in condition_edges
            if _normalize_branch_value(getattr(edge, "branch", None)) == target_branch
        ]
        if explicit:
            explicit.sort(key=lambda edge: getattr(edge, "order", None) if isinstance(getattr(edge, "order", None), int) else 10**9)
            return explicit[0].target, "metadata"

        defaults = [
            edge for edge in condition_edges
            if _normalize_branch_value(getattr(edge, "branch", None)) == "default"
        ]
        if defaults:
            defaults.sort(key=lambda edge: getattr(edge, "order", None) if isinstance(getattr(edge, "order", None), int) else 10**9)
            return defaults[0].target, "default"

    if len(successors) >= 2:
        return successors[0 if condition_result else 1], "legacy-order"
    if len(successors) == 1:
        return successors[0], "single-successor"
    return None, "no-successor"


def execute_subflow_loop(executor, graph, ctx, adjacency_map, pending_nodes, boundary_end_node):
    failed_node_ids = set()

    while pending_nodes:
        node_id, node = pop_next_subflow_node(graph, pending_nodes)
        if not node:
            ctx.add_log(LogLevel.WARNING, f"Node {node_id} not found", node_id=node_id)
            continue

        # Stop enqueuing new nodes once end marker is set
        if ctx.state.get("ended"):
            ctx.add_log(LogLevel.INFO, f"Workflow ended at: {node_id}", node_id=node_id)
            break

        try:
            node_result = executor._execute_node_sync(node, ctx)
            if not node_result.success:
                failed_node_ids.add(node_id)
                if node_result.error and 'step budget' in node_result.error.lower():
                    ctx.add_log(LogLevel.WARNING, f"Stopped at step limit: {ctx.steps_executed}")
                    return build_partial_subflow_response(ctx, node_result.error)
        except RuntimeError as error:
            if 'step budget' in str(error).lower():
                ctx.add_log(LogLevel.WARNING, f"Stopped at step limit: {ctx.steps_executed}")
                return build_partial_subflow_response(ctx, str(error))
            raise
        except Exception as error:
            ctx.add_log(LogLevel.ERROR, f"Failed to execute node {node_id}: {error}", node_id=node_id, details={'exception': str(error)})
            return build_partial_subflow_response(ctx, str(error))

        if node_id not in failed_node_ids and executor._should_requeue_successors(node, ctx):
            # For condition nodes, only enqueue the branch matching condition_result
            if node.type == "condition":
                branch = ctx.state.get("condition_result")
                successors = adjacency_map.get(node_id, [])
                if successors:
                    target, reason = _select_condition_successor(graph, node_id, successors, branch)
                    if target:
                        pending_nodes.append(target)
                        ctx.add_log(
                            LogLevel.INFO,
                            f"Condition branch taken: {branch} => enqueued {target} ({reason})",
                            node_id=node_id
                        )
                continue

            if node.type == "paginate":
                if not bool(ctx.state.get("last_pagination_advanced")):
                    ctx.add_log(
                        LogLevel.INFO,
                        f"Pagination stopped requeue at {node_id}; page did not advance",
                        node_id=node_id,
                    )
                    continue

            skipped_boundary = boundary_end_node in adjacency_map.get(node_id, []) if boundary_end_node else False
            if skipped_boundary:
                ctx.add_log(LogLevel.INFO, f"Reached boundary node: {boundary_end_node}", node_id=boundary_end_node)
            enqueue_successors(pending_nodes, adjacency_map, node_id, boundary_end_node)

    return None
