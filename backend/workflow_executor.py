"""Workflow executor for MVP node types with scoped side-effect safety.

Architecture note:
- workflow_graph.py: graph traversal algorithms (node map, adjacency map, entry node finding)
- workflow_handlers.py: individual node type handlers (open_page, select_list, etc.)
- This module: orchestration of graph traversal + node execution, plus ExecutionContext
"""

import time
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from copy import deepcopy
from .workflow_schemas import (
    WorkflowGraph, WorkflowNode, WorkflowEdge, NodeData,
    LogLevel, ExecutionLog, NodeResult,
    TestNodeRequest, TestNodeResponse,
    TestSubflowRequest, TestSubflowResponse,
    SubflowBoundary,
)
from .async_bridge import run_blocking
from .browser_session import PageSession, page_session_mgr
from .workflow_graph import (
    build_node_map,
    find_entry_node,
    find_node_by_id,
)
from .workflow_handlers import node_handlers
from .workflow_executor_helpers import (
    build_missing_node_response,
    build_partial_subflow_response,
    build_session_expired_node_response,
    build_subflow_exception_response,
    build_subflow_missing_entry_response,
    build_subflow_session_expired_response,
    build_subflow_success_response,
    build_test_node_exception_response,
    get_or_create_session,
    resolve_subflow_limits,
    resolve_test_node_limits,
)
from .workflow_executor_traversal import (
    collect_prerequisites,
    create_subflow_queue,
    get_subflow_adjacency_map,
)
from .workflow_executor_orchestration import execute_subflow_loop

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
                return build_missing_node_response(request.node_id, target_node)

            session = get_or_create_session(request.session_id)
            if not session:
                return build_session_expired_node_response(request.node_id, target_node)

            # Create execution context
            limits = resolve_test_node_limits(request, target_node)
            ctx = ExecutionContext(
                session=session,
                max_steps=limits["max_steps"],
                max_items=limits["max_items"],
                max_pages=limits["max_pages"],
            )

            # For test-node, execute only prerequisites + target node
            prerequisites = collect_prerequisites(request.graph, request.node_id)

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
            return build_test_node_exception_response(
                request.node_id,
                target_node if 'target_node' in locals() else None,
                e,
                ctx.logs if ctx else [],
            )

    def _test_subflow_sync(self, request: TestSubflowRequest) -> TestSubflowResponse:
        """Synchronously test a subflow within graph boundaries."""
        ctx = None

        try:
            # Find entry node
            entry_node = find_entry_node(request.graph)
            if not entry_node:
                return build_subflow_missing_entry_response()

            session = get_or_create_session(request.session_id)
            if not session:
                return build_subflow_session_expired_response()

            # Set up boundaries and limits
            boundary = request.boundary or SubflowBoundary()

            limits = resolve_subflow_limits(request.graph, boundary)
            ctx = ExecutionContext(
                session=session,
                max_steps=limits["max_steps"],
                max_items=limits["max_items"],
                max_pages=limits["max_pages"],
                boundary_start_node=boundary.start_node_id,
                boundary_end_node=boundary.end_node_id
            )

            # Build traversal map
            adjacency_map = get_subflow_adjacency_map(request.graph)

            # Execute from start node (or entry if not specified). Requeue repeated
            # nodes so max_steps, not visited-state alone, bounds cyclic graphs.
            pending_nodes = create_subflow_queue(entry_node.id, boundary.start_node_id)

            partial_response = execute_subflow_loop(
                self,
                request.graph,
                ctx,
                adjacency_map,
                pending_nodes,
                boundary.end_node_id,
            )
            if partial_response is not None:
                return partial_response

            return build_subflow_success_response(ctx)

        except Exception as e:
            logger.exception("test_subflow failed")
            return build_subflow_exception_response(ctx, e)


# Singleton executor instance
executor = WorkflowExecutor()
