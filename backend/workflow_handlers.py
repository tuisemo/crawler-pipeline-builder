"""Node execution handlers for workflow executor.

Separated from workflow_executor.py to allow independent testing
of node handler logic without full graph traversal context.
"""

import logging
from typing import Any, Dict, Optional

from .workflow_schemas import NodeResult, LogLevel
from extraction.selector_tester import SelectorTester

logger = logging.getLogger(__name__)


class NodeHandlers:
    """Encapsulates all MVP node type handlers.

    Each handler follows the signature:
        def handle(node, ctx, result)
    Where:
        - node: WorkflowNode being executed
        - ctx: ExecutionContext with session, state, logs, etc.
        - result: NodeResult that should be populated by the handler
    """

    def __init__(self):
        self.selector_tester = SelectorTester()

    def handle_open_page(self, node, ctx, result):
        """Execute open_page node."""
        url = node.data.url
        if not url:
            result.error = "URL is required for open_page node"
            return

        try:
            ctx.session.navigate(url, timeout=30000)
            ctx.add_log(LogLevel.INFO, f"Navigated to: {url}", node_id=node.id)
            result.result = {"url": url, "status": "navigated"}
        except Exception as e:
            result.error = f"Failed to navigate to URL: {e}"
            raise

    def handle_select_list(self, node, ctx, result):
        """Execute select_list node."""
        selector = node.data.item_selector
        if not selector:
            result.error = "item_selector is required for select_list node"
            return

        try:
            test_result = self.selector_tester.test_selector(
                ctx.session.page,
                selector,
                max_samples=ctx.max_items
            )

            result.result = {
                "match_count": test_result.match_count,
                "samples": test_result.sample_items
            }
            ctx.state["item_selector"] = selector
            ctx.state["item_count"] = test_result.match_count
            ctx.add_log(LogLevel.INFO, f"Found {test_result.match_count} items", node_id=node.id)

        except Exception as e:
            result.error = f"Failed to select items: {e}"
            raise

    def handle_extract_field(self, node, ctx, result):
        """Execute extract_field node."""
        fields = node.data.fields
        item_selector = ctx.state.get("item_selector")

        if not fields:
            result.error = "fields are required for extract_field node"
            return

        if not item_selector:
            result.error = "item_selector not found in context (need select_list first)"
            return

        try:
            records = self.selector_tester.extract_fields_from_items(
                ctx.session.page,
                item_selector,
                fields
            )[:ctx.max_items]

            result.result = {
                "extracted_count": len(records),
                "records": records
            }
            ctx.records.extend(records)
            ctx.state["extracted_records"] = ctx.records
            ctx.add_log(LogLevel.INFO, f"Extracted {len(records)} records", node_id=node.id)

        except Exception as e:
            result.error = f"Failed to extract fields: {e}"
            raise

    def handle_paginate(self, node, ctx, result):
        """Execute paginate node (bounded for testing)."""
        selector = node.data.pagination_selector
        strategy = node.data.pagination_strategy or "click_next"

        if not selector:
            result.error = "pagination_selector is required for paginate node"
            return

        try:
            elements = ctx.session.page.query_selector_all(selector)
            exists = len(elements) > 0

            message = "Pagination selector found" if exists else "Pagination selector not found"
            result.result = {
                "selector": selector,
                "strategy": strategy,
                "found": exists,
                "message": f"{message} (limited to single-page testing)"
            }
            ctx.add_log(LogLevel.INFO, f"Pagination check: {'found' if exists else 'not found'}", node_id=node.id)

        except Exception as e:
            result.error = f"Failed to check pagination: {e}"
            raise

    def handle_emit_record(self, node, ctx, result):
        """Execute emit_record node."""
        records = ctx.state.get("extracted_records", [])

        bounded_records = records[:ctx.max_items]
        result.result = {
            "emitted_count": len(bounded_records),
            "records": bounded_records
        }
        ctx.add_log(LogLevel.INFO, f"Emitted {len(records)} records", node_id=node.id)

    def handle_loop(self, node, ctx, result):
        """Execute loop node.

        Reads the item set produced by a prior select_list from ctx.state and
        sets loop iteration context so downstream extract_field nodes know
        which item they are operating on. This replaces the legacy behavior
        where extract_field would do full-page batch extraction.

        Execution flow:
        1. Read item_count from ctx.state (set by upstream select_list).
        2. Set loop_bound = min(node.max_items, ctx.max_items, item_count).
        3. Write ctx.state["loop_bound"] and ctx.state["loop_on_error"] for
           downstream nodes to read.
        4. Do NOT expand sub-flows here; the orchestration loop handles
           re-queuing downstream nodes per iteration.
        """
        item_count = ctx.state.get("item_count", 0)
        node_max = node.data.max_items if node.data.max_items else ctx.max_items
        ctx_max = ctx.max_items
        loop_bound = min(node_max, ctx_max, item_count) if item_count > 0 else 0

        on_error = node.data.on_error or "skip"

        ctx.state["loop_bound"] = loop_bound
        ctx.state["loop_on_error"] = on_error
        ctx.state["loop_current_index"] = 0

        result.result = {
            "item_count": item_count,
            "loop_bound": loop_bound,
            "on_error": on_error,
            "note": (
                f"Loop context set: {loop_bound} items "
                f"(max={node_max}, context_limit={ctx_max}, found={item_count})"
            )
        }
        ctx.add_log(
            LogLevel.INFO,
            f"Loop context set: {loop_bound} items (on_error={on_error})",
            node_id=node.id
        )

    def handle_condition(self, node, ctx, result):
        """Execute condition node.

        Evaluates a simple whitelist-based expression against the current
        execution state. Supports operators: exists, not_exists, contains,
        not_contains, equals, not_equals, gt, lt, gte, lte.
        Operands are field names that are looked up from ctx.state or the
        last extracted record.

        Example expressions:
          - "title exists"
          - "price gt 0"
          - "category contains 仪表"
        """
        expression = getattr(node.data, 'condition', None)
        if not expression:
            result.error = "condition field is required for condition node"
            return

        condition_result = self._evaluate_condition(expression, ctx)
        ctx.state["condition_result"] = condition_result

        result.result = {
            "expression": expression,
            "condition_result": condition_result,
            "branch": "true" if condition_result else "false",
        }
        ctx.add_log(
            LogLevel.INFO,
            f"Condition '{expression}' => {condition_result} (branch={('true' if condition_result else 'false')})",
            node_id=node.id
        )

    def _evaluate_condition(self, expression: str, ctx) -> bool:
        """Evaluate a simple whitelist-based condition expression."""
        parts = expression.strip().split(maxsplit=2)
        if len(parts) < 2:
            ctx.add_log(LogLevel.WARNING, f"Condition expression too short: '{expression}'")
            return False

        operator = parts[0].lower()
        operands = parts[1:]

        # Look up operand values from state / last record
        def resolve_operand(operand: str) -> str:
            # Check last extracted record
            records = ctx.state.get("extracted_records", [])
            if records:
                last = records[-1]
                if operand in last:
                    val = last.get(operand)
                    return str(val) if val is not None else ""
            # Check top-level state
            if operand in ctx.state:
                val = ctx.state.get(operand)
                return str(val) if val is not None else ""
            return ""

        def coerce_numeric(val: str):
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        # Whitelist of operators
        if operator == "exists":
            return resolve_operand(operands[0]) != ""

        if operator == "not_exists":
            return resolve_operand(operands[0]) == ""

        if len(operands) < 2:
            return False

        left = resolve_operand(operands[0])
        right = operands[1] if len(operands) > 1 else ""

        if operator == "contains":
            return left and right.lower() in left.lower()
        if operator == "not_contains":
            return left and right.lower() not in left.lower()
        if operator == "equals":
            return left == right
        if operator == "not_equals":
            return left != right

        # Numeric comparisons
        lnum = coerce_numeric(left)
        rnum = coerce_numeric(right)
        if lnum is not None and rnum is not None:
            if operator == "gt":
                return lnum > rnum
            if operator == "lt":
                return lnum < rnum
            if operator == "gte":
                return lnum >= rnum
            if operator == "lte":
                return lnum <= rnum

        ctx.add_log(LogLevel.WARNING, f"Unknown condition operator: '{operator}'")
        return False

    def handle_end(self, node, ctx, result):
        """Execute end node.

        Sets ctx.state["ended"] = True so the orchestration loop stops
        further enqueuing of successor nodes. This is a safe no-op that
        makes workflow paths explicitly bounded.
        """
        ctx.state["ended"] = True
        result.result = {
            "status": "ended",
            "node_id": node.id,
        }
        ctx.add_log(LogLevel.INFO, f"End node reached: {node.id}", node_id=node.id)

    def dispatch(self, node, ctx, result):
        """Dispatch node execution to the appropriate handler.

        Returns True if the node was handled, False if the node type is unsupported.
        """
        handler_map = {
            "open_page": self.handle_open_page,
            "select_list": self.handle_select_list,
            "extract_field": self.handle_extract_field,
            "paginate": self.handle_paginate,
            "emit_record": self.handle_emit_record,
            "loop": self.handle_loop,
            "condition": self.handle_condition,
            "end": self.handle_end,
        }

        handler = handler_map.get(node.type)
        if handler:
            handler(node, ctx, result)
            return True

        return False


# Singleton handlers instance
node_handlers = NodeHandlers()
