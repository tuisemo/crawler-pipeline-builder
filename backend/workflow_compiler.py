"""Workflow compiler: graph -> deterministic execution plan.

This module converts a DSL workflow graph into a normalized plan object
that can be consumed by prompt generation and future codegen backends.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .workflow_schemas import WorkflowGraph


@dataclass
class ExecutionPlan:
    entry_url: str
    node_types: list[str]
    item_selector: str
    field_specs: list[dict[str, Any]]
    pagination: dict[str, Any]
    limits: dict[str, int]
    edges: list[dict[str, Any]]
    conditions: list[dict[str, Any]]


def _resolve_field(field: dict[str, Any], index: int) -> dict[str, Any]:
    name = field.get("name") or field.get("field_name") or f"field_{index + 1}"
    selector = field.get("selector") or field.get("css") or ""
    extraction_type = field.get("type") or field.get("extraction_type") or "text"
    resolved = {
        "name": name,
        "selector": selector,
        "type": extraction_type,
    }
    clean_data_type = field.get("clean_data_type")
    if isinstance(clean_data_type, str) and clean_data_type.strip():
        resolved["clean_data_type"] = clean_data_type.strip()
    normalized_sample = field.get("normalized_sample")
    if isinstance(normalized_sample, str) and normalized_sample.strip():
        resolved["normalized_sample"] = normalized_sample.strip()
    return resolved


def _coerce_limit(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def compile_graph_to_plan(graph: WorkflowGraph) -> ExecutionPlan:
    """Compile a WorkflowGraph into a deterministic execution plan."""
    entry_url = ""
    item_selector = ""
    field_specs: list[dict[str, Any]] = []
    pagination = {
        "strategy": "click_next",
        "selector": "",
        "max_pages": 1,
    }
    limits = {
        "max_items": 50,
        "max_steps": 100,
        "max_pages": 10,
    }
    explicit_max_items: list[int] = []
    conditions: list[dict[str, Any]] = []

    node_types = [node.type for node in graph.nodes]
    for node in graph.nodes:
        data = node.data
        if node.type == "open_page":
            entry_url = data.url or entry_url
            open_page_max_items = _coerce_limit(data.max_items)
            if open_page_max_items is not None:
                explicit_max_items.append(open_page_max_items)
            if data.max_steps is not None:
                limits["max_steps"] = data.max_steps
        elif node.type == "select_list":
            item_selector = data.item_selector or item_selector
            select_max_items = _coerce_limit(data.max_items)
            if select_max_items is not None:
                explicit_max_items.append(select_max_items)
        elif node.type == "extract_field":
            raw_fields = data.fields or []
            field_specs = [
                _resolve_field(raw_field, index)
                for index, raw_field in enumerate(raw_fields)
            ]
            extract_max_items = _coerce_limit(data.max_items)
            if extract_max_items is not None:
                explicit_max_items.append(extract_max_items)
        elif node.type == "paginate":
            pagination["selector"] = data.pagination_selector or pagination["selector"]
            pagination["strategy"] = data.pagination_strategy or pagination["strategy"]
            if data.max_pages is not None:
                pagination["max_pages"] = data.max_pages
                limits["max_pages"] = data.max_pages
        elif node.type == "condition":
            conditions.append(
                {
                    "node_id": node.id,
                    "expression": data.condition or "",
                    "mode": data.expression_mode or "simple",
                }
            )
        elif node.type == "loop":
            loop_max_items = _coerce_limit(data.max_items)
            if loop_max_items is not None:
                explicit_max_items.append(loop_max_items)

    if explicit_max_items:
        limits["max_items"] = min(explicit_max_items)

    edges = [
        {
            "id": edge.id,
            "source": edge.source,
            "target": edge.target,
            "branch": getattr(edge, "branch", None),
            "label": getattr(edge, "label", None),
            "order": getattr(edge, "order", None),
        }
        for edge in graph.edges
    ]

    return ExecutionPlan(
        entry_url=entry_url,
        node_types=node_types,
        item_selector=item_selector,
        field_specs=field_specs,
        pagination=pagination,
        limits=limits,
        edges=edges,
        conditions=conditions,
    )


def execution_plan_to_dict(plan: ExecutionPlan) -> dict[str, Any]:
    return asdict(plan)
