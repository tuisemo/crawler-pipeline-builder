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
        }

        handler = handler_map.get(node.type)
        if handler:
            handler(node, ctx, result)
            return True

        return False


# Singleton handlers instance
node_handlers = NodeHandlers()
