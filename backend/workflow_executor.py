"""Workflow executor for MVP node types with scoped side-effect safety.

Architecture note:
- workflow_graph.py: graph traversal algorithms (node map, adjacency map, entry node finding)
- workflow_handlers.py: individual node type handlers (open_page, select_list, etc.)
- This module: orchestration of graph traversal + node execution, plus ExecutionContext
"""

import time
import logging
from collections import deque
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from copy import deepcopy

from .workflow_schemas import (
    WorkflowGraph, WorkflowNode, WorkflowEdge, NodeData,
    LogLevel, ExecutionLog, NodeResult,
    TestNodeRequest, TestNodeResponse,
    TestSubflowRequest, TestSubflowResponse,
    SubflowBoundary
)
from .async_bridge import run_blocking
from .browser_session import PageSession, page_session_mgr
from .workflow_graph import (
    build_node_map,
    build_adjacency_map,
    find_entry_node,
    find_node_by_id,
    get_prerequisite_nodes,
)
from .workflow_handlers import node_handlers

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for workflow execution with scoped side effects."""
    session: PageSession
    state: Dict[str, Any] = field(default_factory=dict)
    logs: List[ExecutionLog] = field(default_factory=list)
    node_results: List[NodeResult] = field(default_factory=list)
    records: List[Dict[str, Any]] = field(default_factory=list)
    executed_nodes: Set[str] = field(default_factory=set)
    node_state_fingerprints: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    steps_executed: int = 0
    start_time: float = field(default_factory=time.time)

    # Execution limits
    max_steps: int = 100
    max_items: int = 50
    max_pages: int = 10

    # Subflow boundaries
    boundary_start_node: Optional[str] = None
    boundary_end_node: Optional[str] = None

    def add_log(self, level: LogLevel, message: str, node_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """Add an execution log."""
        log = ExecutionLog(
            timestamp=time.time(),
            level=level,
            node_id=node_id,
            message=message,
            details=details
        )
        self.logs.append(log)
        logger.log(getattr(logging, level.value.upper()), message)

    def increment_step(self):
        """Increment step counter and check limits."""
        if self.steps_executed >= self.max_steps:
            raise RuntimeError(f"Max steps ({self.max_steps}) exceeded")
        self.steps_executed += 1


class WorkflowExecutor:
    """Executes workflow graphs with bounded, safe execution."""

    MVP_NODE_TYPES = {
        "open_page",
        "select_list",
        "loop",
        "extract_field",
        "condition",
        "paginate",
        "emit_record",
        "end"
    }

    def __init__(self):
        pass

    def _capture_revisit_fingerprint(self, ctx: ExecutionContext) -> Dict[str, Any]:
        """Capture execution state that indicates whether revisiting can do new work."""
        state = deepcopy(ctx.state)
        if "extracted_records" in state:
            state["extracted_records"] = state["extracted_records"][:ctx.max_items]
        return {
            "state": state,
            "records": deepcopy(ctx.records[:ctx.max_items]),
            "current_url": getattr(ctx.session.page, "url", None),
        }

    def _should_requeue_successors(self, node: WorkflowNode, ctx: ExecutionContext) -> bool:
        """Return False when a successful revisit leaves execution state unchanged."""
        fingerprint = self._capture_revisit_fingerprint(ctx)
        previous = ctx.node_state_fingerprints.get(node.id)
        ctx.node_state_fingerprints[node.id] = fingerprint

        if previous is None or previous != fingerprint:
            return True

        ctx.add_log(
            LogLevel.INFO,
            f"Skipped revisit of {node.id}; execution state did not advance",
            node_id=node.id,
            details={"reason": "state_not_advanced"},
        )
        return False

    def _execute_node_sync(self, node: WorkflowNode, ctx: ExecutionContext) -> NodeResult:
        """Execute a single node synchronously and return its result."""
        start_time = time.time()
        ctx.add_log(LogLevel.INFO, f"Executing node: {node.id} ({node.type})", node_id=node.id)

        result = NodeResult(
            node_id=node.id,
            node_type=node.type,
            success=False,
            started_at=start_time,
            completed_at=0,
            logs=[],
            result=None,
            error=None
        )

        try:
            ctx.increment_step()

            # Delegate to handlers module; unsupported types fall through to error
            handled = node_handlers.dispatch(node, ctx, result)
            if not handled:
                result.error = f"Unsupported node type: {node.type}"
                result.result = {"status": "unsupported", "node_type": node.type}
                ctx.add_log(LogLevel.ERROR, result.error, node_id=node.id)

            result.success = result.error is None

        except Exception as e:
            result.error = str(e)
            ctx.add_log(LogLevel.ERROR, f"Node execution failed: {e}", node_id=node.id, details={"exception": str(e)})

        result.completed_at = time.time()
        ctx.node_results.append(result)
        ctx.executed_nodes.add(node.id)

        return result

    async def _execute_node(self, node: WorkflowNode, ctx: ExecutionContext) -> NodeResult:
        return await run_blocking(lambda: self._execute_node_sync(node, ctx))

    async def test_node(self, request: TestNodeRequest) -> TestNodeResponse:
        """Test a single node with minimal prerequisites."""
        return await run_blocking(lambda: self._test_node_sync(request))

    async def test_subflow(self, request: TestSubflowRequest) -> TestSubflowResponse:
        """Test a subflow within graph boundaries."""
        return await run_blocking(lambda: self._test_subflow_sync(request))

    def _test_node_sync(self, request: TestNodeRequest) -> TestNodeResponse:
        """Synchronously test a single node with minimal prerequisites."""
        ctx = None

        try:
            # Validate node exists
            target_node = find_node_by_id(request.graph, request.node_id)
            if not target_node:
                return TestNodeResponse(
                    success=False,
                    node_id=request.node_id,
                    result=NodeResult(
                        node_id=request.node_id,
                        node_type="unknown",
                        success=False,
                        started_at=time.time(),
                        completed_at=time.time()
                    ),
                    error=f"Node {request.node_id} not found in graph",
                    session_expired=False
                )

            # Get or create session
            if request.session_id:
                session = page_session_mgr.get(request.session_id)
                if not session:
                    return TestNodeResponse(
                        success=False,
                        node_id=request.node_id,
                        result=NodeResult(
                            node_id=request.node_id,
                            node_type=target_node.type,
                            success=False,
                            started_at=time.time(),
                            completed_at=time.time()
                        ),
                        error="Session not found or expired",
                        session_expired=True
                    )
            else:
                session = page_session_mgr.create()

            # Create execution context
            ctx = ExecutionContext(
                session=session,
                max_steps=request.max_steps,
                max_items=request.max_items
            )

            # For test-node, execute only prerequisites + target node
            adj_map = build_adjacency_map(request.graph)
            prerequisites = get_prerequisite_nodes(request.graph, request.node_id, adj_map)

            # Execute prerequisites first (bounded)
            for prereq_node in prerequisites:
                if prereq_node.id in ctx.executed_nodes:
                    continue
                try:
                    self._execute_node_sync(prereq_node, ctx)
                except Exception as e:
                    ctx.add_log(LogLevel.WARNING, f"Prerequisite {prereq_node.id} failed: {e}")
                    # Continue anyway - test-node should be lenient on prerequisites

            # Execute the target node
            node_result = self._execute_node_sync(target_node, ctx)

            return TestNodeResponse(
                success=node_result.success,
                node_id=request.node_id,
                result=node_result,
                logs=ctx.logs,
                error=node_result.error,
                session_expired=False
            )

        except Exception as e:
            logger.exception("test_node failed")
            return TestNodeResponse(
                success=False,
                node_id=request.node_id,
                result=NodeResult(
                    node_id=request.node_id,
                    node_type=target_node.type if target_node else "unknown",
                    success=False,
                    started_at=time.time(),
                    completed_at=time.time()
                ),
                logs=ctx.logs if ctx else [],
                error=str(e),
                session_expired=False
            )

    def _test_subflow_sync(self, request: TestSubflowRequest) -> TestSubflowResponse:
        """Synchronously test a subflow within graph boundaries."""
        ctx = None

        try:
            # Find entry node
            entry_node = find_entry_node(request.graph)
            if not entry_node:
                return TestSubflowResponse(
                    success=False,
                    partial=False,
                    node_results=[],
                    logs=[],
                    records=[],
                    error="No open_page entry node found",
                    session_expired=False,
                    steps_executed=0
                )

            # Get or create session
            if request.session_id:
                session = page_session_mgr.get(request.session_id)
                if not session:
                    return TestSubflowResponse(
                        success=False,
                        partial=False,
                        node_results=[],
                        logs=[],
                        records=[],
                        error="Session not found or expired",
                        session_expired=True,
                        steps_executed=0
                    )
            else:
                session = page_session_mgr.create()

            # Set up boundaries and limits
            boundary = request.boundary or SubflowBoundary()

            ctx = ExecutionContext(
                session=session,
                max_steps=boundary.max_steps or 100,
                max_items=boundary.max_items or 50,
                max_pages=boundary.max_pages or 10,
                boundary_start_node=boundary.start_node_id,
                boundary_end_node=boundary.end_node_id
            )

            # Build traversal map
            adj_map = build_adjacency_map(request.graph)
            failed_node_ids = set()

            # Execute from start node (or entry if not specified). Requeue repeated
            # nodes so max_steps, not visited-state alone, bounds cyclic graphs.
            start_node_id = boundary.start_node_id or entry_node.id
            pending_nodes = deque([start_node_id])

            while pending_nodes:
                node_id = pending_nodes.popleft()
                node = find_node_by_id(request.graph, node_id)
                if not node:
                    ctx.add_log(LogLevel.WARNING, f"Node {node_id} not found", node_id=node_id)
                    continue

                try:
                    node_result = self._execute_node_sync(node, ctx)
                    if not node_result.success:
                        failed_node_ids.add(node_id)
                        if node_result.error and "Max steps" in node_result.error:
                            ctx.add_log(LogLevel.WARNING, f"Stopped at step limit: {ctx.steps_executed}")
                            return TestSubflowResponse(
                                success=False,
                                partial=True,
                                node_results=ctx.node_results,
                                logs=ctx.logs,
                                records=ctx.records[:ctx.max_items],
                                error=node_result.error,
                                session_expired=False,
                                steps_executed=ctx.steps_executed
                            )
                except RuntimeError as e:
                    if "Max steps" in str(e):
                        ctx.add_log(LogLevel.WARNING, f"Stopped at step limit: {ctx.steps_executed}")
                        return TestSubflowResponse(
                            success=False,
                            partial=True,
                            node_results=ctx.node_results,
                            logs=ctx.logs,
                            records=ctx.records[:ctx.max_items],
                            error=str(e),
                            session_expired=False,
                            steps_executed=ctx.steps_executed
                        )
                    raise
                except Exception as e:
                    ctx.add_log(LogLevel.ERROR, f"Failed to execute node {node_id}: {e}", node_id=node_id, details={"exception": str(e)})
                    return TestSubflowResponse(
                        success=False,
                        partial=True,
                        node_results=ctx.node_results,
                        logs=ctx.logs,
                        records=ctx.records[:ctx.max_items],
                        error=str(e),
                        session_expired=False,
                        steps_executed=ctx.steps_executed
                    )

                if node_id not in failed_node_ids and self._should_requeue_successors(node, ctx):
                    for next_node_id in adj_map.get(node_id, []):
                        if boundary.end_node_id and next_node_id == boundary.end_node_id:
                            ctx.add_log(LogLevel.INFO, f"Reached boundary node: {next_node_id}", node_id=next_node_id)
                            continue
                        pending_nodes.append(next_node_id)

            return TestSubflowResponse(
                success=not any(r.error for r in ctx.node_results),
                partial=False,
                node_results=ctx.node_results,
                logs=ctx.logs,
                records=ctx.records[:ctx.max_items],
                error=None,
                session_expired=False,
                steps_executed=ctx.steps_executed
            )

        except Exception as e:
            logger.exception("test_subflow failed")
            if ctx:
                ctx.add_log(LogLevel.ERROR, f"Subflow execution failed: {e}", details={"exception": str(e)})
            return TestSubflowResponse(
                success=False,
                partial=True,
                node_results=ctx.node_results if ctx else [],
                logs=ctx.logs if ctx else [],
                records=ctx.records[:ctx.max_items] if ctx else [],
                error=str(e),
                session_expired=False,
                steps_executed=ctx.steps_executed if ctx else 0
            )


# Singleton executor instance
executor = WorkflowExecutor()
