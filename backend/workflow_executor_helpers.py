"""Helper utilities for workflow executor session and response assembly."""

from __future__ import annotations

import time
from typing import Optional

from .browser_session import page_session_mgr
from .workflow_schemas import (
    LogLevel,
    NodeResult,
    TestNodeResponse,
    TestSubflowResponse,
    WorkflowNode,
)


def get_or_create_session(session_id: Optional[str]):
    """Return an existing session by id or create a new one."""
    if session_id:
        session = page_session_mgr.get(session_id)
        if session and session.is_alive():
            return session
        if session:
            page_session_mgr.close(session_id)
    return page_session_mgr.create()


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
        records=ctx.records[:ctx.max_items],
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
        records=ctx.records[:ctx.max_items],
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


