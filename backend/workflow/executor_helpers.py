"""Helper utilities for workflow executor session and response assembly."""

from __future__ import annotations

import time
from typing import Optional

from backend.runtime.browser_session import page_session_mgr
from backend.core.settings import get_settings
from backend.workflow.schemas import (
    LogLevel,
    NodeResult,
    SubflowBoundary,
    TestNodeResponse,
    TestSubflowResponse,
    WorkflowGraph,
    WorkflowNode,
)


def _positive_int(value) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _node_limit_values(graph: WorkflowGraph, field_name: str) -> list[int]:
    values: list[int] = []
    for node in graph.nodes:
        value = _positive_int(getattr(node.data, field_name, None))
        if value is not None:
            values.append(value)
    return values


def resolve_test_node_limits(request, target_node: WorkflowNode) -> dict[str, int]:
    """Resolve single-node execution limits.

    Single-node tests now honor only explicit pagination boundaries.
    """
    settings = get_settings()
    return {
        "max_pages": _positive_int(getattr(target_node.data, "max_pages", None)) or settings.default_max_pages,
    }


def resolve_subflow_limits(graph: WorkflowGraph, boundary: SubflowBoundary) -> dict[str, int]:
    """Resolve subflow execution limits.

    Priority: request boundary > explicit node data > settings defaults.
    """
    settings = get_settings()
    node_max_pages = _node_limit_values(graph, "max_pages")
    return {
        "max_pages": _positive_int(boundary.max_pages) or (min(node_max_pages) if node_max_pages else settings.default_max_pages),
    }


def get_or_create_session(session_id: Optional[str], agent_id: Optional[str] = None):
    """Return an existing session by id or create a new one."""
    if session_id:
        session = page_session_mgr.get(session_id)
        if session and session.is_alive():
            return session
        if session:
            page_session_mgr.close(session_id)
        return None
    return page_session_mgr.create(agent_id=agent_id)


def build_missing_node_response(node_id: str, target_node: Optional[WorkflowNode]) -> TestNodeResponse:
    node_type = target_node.type if target_node else 'unknown'
    now = time.time()
    return TestNodeResponse(
        success=False,
        node_id=node_id,
        result=NodeResult(
            node_id=node_id,
            node_type=node_type,
            success=False,
            started_at=now,
            completed_at=now,
        ),
        error=f"Node {node_id} not found in graph",
        session_expired=False,
    )


def build_session_expired_node_response(node_id: str, target_node: WorkflowNode) -> TestNodeResponse:
    now = time.time()
    return TestNodeResponse(
        success=False,
        node_id=node_id,
        result=NodeResult(
            node_id=node_id,
            node_type=target_node.type,
            success=False,
            started_at=now,
            completed_at=now,
        ),
        error='Session not found or expired',
        session_expired=True,
    )


def build_test_node_exception_response(node_id: str, target_node: Optional[WorkflowNode], error: Exception, logs):
    now = time.time()
    return TestNodeResponse(
        success=False,
        node_id=node_id,
        result=NodeResult(
            node_id=node_id,
            node_type=target_node.type if target_node else 'unknown',
            success=False,
            started_at=now,
            completed_at=now,
        ),
        logs=logs,
        error=str(error),
        session_expired=False,
    )


def build_subflow_missing_entry_response() -> TestSubflowResponse:
    return TestSubflowResponse(
        success=False,
        partial=False,
        node_results=[],
        logs=[],
        records=[],
        error='No open_page entry node found',
        session_expired=False,
        steps_executed=0,
    )


def build_subflow_session_expired_response() -> TestSubflowResponse:
    return TestSubflowResponse(
        success=False,
        partial=False,
        node_results=[],
        logs=[],
        records=[],
        error='Session not found or expired',
        session_expired=True,
        steps_executed=0,
    )


def build_partial_subflow_response(ctx, error: str, session_expired: bool = False) -> TestSubflowResponse:
    return TestSubflowResponse(
        success=False,
        partial=True,
        node_results=ctx.node_results,
        logs=ctx.logs,
        records=ctx.records[:ctx.record_preview_limit],
        error=error,
        session_expired=session_expired,
        steps_executed=ctx.steps_executed,
    )


def build_subflow_success_response(ctx) -> TestSubflowResponse:
    return TestSubflowResponse(
        success=not any(result.error for result in ctx.node_results),
        partial=False,
        node_results=ctx.node_results,
        logs=ctx.logs,
        records=ctx.records[:ctx.record_preview_limit],
        error=None,
        session_expired=False,
        steps_executed=ctx.steps_executed,
    )


def build_subflow_exception_response(ctx, error: Exception) -> TestSubflowResponse:
    if ctx:
        ctx.add_log(LogLevel.ERROR, f'Subflow execution failed: {error}', details={'exception': str(error)})
        return build_partial_subflow_response(ctx, str(error))
    return TestSubflowResponse(
        success=False,
        partial=True,
        node_results=[],
        logs=[],
        records=[],
        error=str(error),
        session_expired=False,
        steps_executed=0,
    )
