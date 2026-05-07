"""Node execution handlers for workflow executor.

Separated from workflow_executor.py to allow independent testing
of node handler logic without full graph traversal context.
"""

import logging
import time
from typing import Any, Dict, Optional

from backend.runtime.record_sinks import RecordSinkError, emit_records
from backend.workflow.schemas import NodeResult, LogLevel
from backend.extraction.selector_tester import SelectorTester

logger = logging.getLogger(__name__)

PAGINATION_UPDATE_TIMEOUT_MS = 6000
PAGINATION_POLL_INTERVAL_MS = 250


def _is_extension_session(session) -> bool:
    return hasattr(session, "test_selector") and hasattr(session, "extract_fields")


def _session_url(session) -> str:
    return getattr(getattr(session, "page", None), "url", getattr(session, "url", "")) or ""


def _collect_planned_field_names(fields: list[dict[str, Any]] | None) -> list[str]:
    if not fields:
        return []

    planned_fields: list[str] = []
    seen = set()
    for field in fields:
        if not isinstance(field, dict):
            continue
        field_name = str(field.get("name") or field.get("field_name") or "").strip()
        if not field_name or field_name in seen:
            continue
        seen.add(field_name)
        planned_fields.append(field_name)
    return planned_fields


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
            ctx.state["pages_processed"] = 1
            ctx.state["last_pagination_advanced"] = False
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
            if _is_extension_session(ctx.session):
                ext_result = ctx.session.test_selector(
                    selector,
                    max_samples=ctx.selector_sample_limit,
                )
                match_count = int(ext_result.get("count", 0))
                sample_items = ext_result.get("elements", [])
            else:
                test_result = self.selector_tester.test_selector(
                    ctx.session.page,
                    selector,
                    max_samples=ctx.selector_sample_limit
                )
                match_count = test_result.match_count
                sample_items = test_result.sample_items

            result.result = {
                "match_count": match_count,
                "samples": sample_items
            }
            ctx.state["item_selector"] = selector
            ctx.state["item_count"] = match_count
            if hasattr(ctx.session, "page"):
                setattr(ctx.session.page, "_last_item_selector", selector)
            ctx.add_log(LogLevel.INFO, f"Found {match_count} items", node_id=node.id)

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
            planned_fields = _collect_planned_field_names(fields)
            if planned_fields:
                existing_planned = ctx.state.setdefault("planned_record_fields", [])
                for field_name in planned_fields:
                    if field_name not in existing_planned:
                        existing_planned.append(field_name)

            if _is_extension_session(ctx.session):
                records = ctx.session.extract_fields(item_selector, fields)
            else:
                records = self.selector_tester.extract_fields_from_items(
                    ctx.session.page,
                    item_selector,
                    fields
                )

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
        """Execute paginate node with bounded real page advancement."""
        selector = node.data.pagination_selector
        strategy = (node.data.pagination_strategy or "click_next").strip().lower()

        if not selector:
            result.error = "pagination_selector is required for paginate node"
            return

        try:
            if _is_extension_session(ctx.session):
                selector_payload = ctx.session.test_selector(selector, max_samples=1)
                exists = int(selector_payload.get("count", 0)) > 0
            else:
                elements = ctx.session.page.query_selector_all(selector)
                exists = len(elements) > 0
            current_page = int(ctx.state.get("pages_processed") or 1)
            limit_reached = current_page >= ctx.max_pages
            advanced = False
            message = "Pagination selector found" if exists else "Pagination selector not found"

            if exists and not limit_reached:
                if _is_extension_session(ctx.session):
                    if strategy in {"click_next", "load_more"}:
                        click_result = ctx.session.click_element(selector)
                        advanced = bool(click_result.get("clicked")) and (
                            bool(click_result.get("domChanged")) or strategy == "load_more"
                        )
                    elif strategy == "infinite_scroll":
                        before_count = int(ctx.state.get("item_count") or 0)
                        ctx.session.scroll_to_bottom()
                        after_count = int(
                            ctx.session.test_selector(ctx.state.get("item_selector", ""), max_samples=1).get("count", before_count)
                        )
                        advanced = after_count >= before_count
                else:
                    if strategy in {"click_next", "load_more"}:
                        advanced = self._advance_by_click(ctx.session.page, elements[0])
                    elif strategy == "infinite_scroll":
                        advanced = self._advance_by_scroll(ctx.session.page)

                if advanced:
                    current_page += 1
                    ctx.state["pages_processed"] = current_page
                    ctx.state["last_pagination_advanced"] = True
                    message = f"Advanced to page {current_page}"
                else:
                    ctx.state["last_pagination_advanced"] = False
                    message = f"Pagination control was found but did not advance via {strategy}; list content update was not confirmed"
            else:
                ctx.state["last_pagination_advanced"] = False
                if limit_reached:
                    message = f"Pagination limit reached at page {current_page}"

            result.result = {
                "selector": selector,
                "strategy": strategy,
                "found": exists,
                "advanced": advanced,
                "page_number": current_page,
                "max_pages": ctx.max_pages,
                "message": message,
            }
            ctx.add_log(
                LogLevel.INFO,
                f"Pagination {('advanced' if advanced else 'checked')}: {'found' if exists else 'not found'}",
                node_id=node.id,
                details={"strategy": strategy, "page_number": current_page, "advanced": advanced},
            )

        except Exception as e:
            result.error = f"Failed to check pagination: {e}"
            raise

    def _advance_by_click(self, page, element) -> bool:
        before_snapshot = self._collect_pagination_snapshot(page)
        try:
            if hasattr(element, "scroll_into_view_if_needed"):
                element.scroll_into_view_if_needed(timeout=3000)
            element.click(timeout=5000)
        except TypeError:
            element.click()

        return self._wait_for_pagination_update(page, before_snapshot)

    def _advance_by_scroll(self, page) -> bool:
        before_snapshot = self._collect_pagination_snapshot(page)
        try:
            if hasattr(page, "mouse") and hasattr(page.mouse, "wheel"):
                page.mouse.wheel(0, 2000)
            elif hasattr(page, "evaluate"):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            return False

        return self._wait_for_pagination_update(page, before_snapshot)

    def _wait_for_page_settle(self, page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass

    def _count_visible_items(self, page, item_selector: str | None = None) -> int | None:
        selector = item_selector or getattr(page, "_last_item_selector", None)
        if not selector:
            return None
        try:
            return len(page.query_selector_all(selector))
        except Exception:
            return None

    def _collect_pagination_snapshot(self, page) -> dict[str, Any]:
        selector = getattr(page, "_last_item_selector", None)
        items = []
        if selector:
            try:
                items = page.query_selector_all(selector)
            except Exception:
                items = []

        return {
            "url": getattr(page, "url", None),
            "item_selector": selector,
            "item_count": len(items) if selector else None,
            "item_signatures": [self._item_signature(item) for item in items[:3]],
        }

    def _item_signature(self, item) -> str:
        text = ""
        href = ""
        try:
            text = (item.inner_text() or "").strip()
        except Exception:
            text = ""
        text = " ".join(text.split())[:160]

        try:
            links = item.query_selector_all("a[href]")
        except Exception:
            links = []
        if links:
            try:
                href = str(links[0].get_attribute("href") or "").strip()
            except Exception:
                href = ""

        return f"{text}|{href}"

    def _pagination_state_changed(self, before: dict[str, Any], after: dict[str, Any]) -> bool:
        before_url = before.get("url")
        after_url = after.get("url")
        if before_url and after_url and before_url != after_url:
            return True

        before_count = before.get("item_count")
        after_count = after.get("item_count")
        if before_count is not None and after_count is not None and before_count != after_count:
            return True

        before_signatures = before.get("item_signatures") or []
        after_signatures = after.get("item_signatures") or []
        if before_signatures and after_signatures and before_signatures != after_signatures:
            return True

        return False

    def _wait_for_pagination_update(self, page, before_snapshot: dict[str, Any]) -> bool:
        self._wait_for_page_settle(page)

        if self._pagination_state_changed(before_snapshot, self._collect_pagination_snapshot(page)):
            return True

        deadline = time.monotonic() + (PAGINATION_UPDATE_TIMEOUT_MS / 1000)
        while time.monotonic() < deadline:
            try:
                page.wait_for_timeout(PAGINATION_POLL_INTERVAL_MS)
            except Exception:
                break
            after_snapshot = self._collect_pagination_snapshot(page)
            if self._pagination_state_changed(before_snapshot, after_snapshot):
                return True

        return False

    def handle_emit_record(self, node, ctx, result):
        """Execute emit_record node."""
        records = ctx.state.get("extracted_records", [])
        emit_offsets = ctx.state.setdefault("_emit_offsets", {})
        emit_offset = emit_offsets.get(node.id, 0)
        pending_records = records[emit_offset:]
        emit_offsets[node.id] = len(records)

        result.result = {
            "emitted_count": len(pending_records),
            "records": pending_records,
        }
        try:
            sink_result = emit_records(
                node.data,
                pending_records,
                context={
                    "page_url": _session_url(ctx.session),
                    "run_id": f"ctx-{int(ctx.start_time)}",
                    "planned_fields": ctx.state.get("planned_record_fields", []),
                },
            )
        except RecordSinkError as error:
            result.error = f"Failed to persist emitted records: {error}"
            raise

        if sink_result.get("output_mode") != "memory":
            result.result.update(sink_result)
        ctx.add_log(
            LogLevel.INFO,
            f"Emitted {len(pending_records)} new records",
            node_id=node.id,
            details={"output_mode": sink_result.get("output_mode", "memory")},
        )

    def handle_loop(self, node, ctx, result):
        """Execute loop node.

        Reads the item set produced by a prior select_list from ctx.state and
        sets loop iteration context so downstream extract_field nodes know
        which item they are operating on. This replaces the legacy behavior
        where extract_field would do full-page batch extraction.

        Execution flow:
        1. Read item_count from ctx.state (set by upstream select_list).
        2. Set loop_bound = item_count.
        3. Write ctx.state["loop_bound"] and ctx.state["loop_on_error"] for
           downstream nodes to read.
        4. Do NOT expand sub-flows here; the orchestration loop handles
           re-queuing downstream nodes per iteration.
        """
        item_count = ctx.state.get("item_count", 0)
        loop_bound = item_count if item_count > 0 else 0

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
                f"(found={item_count})"
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
