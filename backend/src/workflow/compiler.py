"""Workflow compiler: graph -> deterministic execution plan.

This module converts a DSL workflow graph into a normalized plan object
that can be consumed by prompt generation and future codegen backends.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from workflow.output_defaults import default_output_config
from workflow.schemas import WorkflowGraph, normalize_field_payload


@dataclass
class ExecutionPlan:
    entry_url: str
    node_types: list[str]
    item_selector: str
    field_specs: list[dict[str, Any]]
    pagination: dict[str, Any]
    output: dict[str, Any]
    limits: dict[str, int]
    edges: list[dict[str, Any]]
    conditions: list[dict[str, Any]]

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
    output = default_output_config()
    limits = {
        "max_pages": 10,
    }
    conditions: list[dict[str, Any]] = []

    node_types = [node.type for node in graph.nodes]
    for node in graph.nodes:
        data = node.data
        if node.type == "open_page":
            entry_url = data.url or entry_url
        elif node.type == "select_list":
            item_selector = data.item_selector or item_selector
        elif node.type == "extract_field":
            raw_fields = data.fields or []
            field_specs = [
                normalize_field_payload(raw_field, index=index)
                for index, raw_field in enumerate(raw_fields)
            ]
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
        elif node.type == "emit_record":
            if data.output_mode:
                output["mode"] = data.output_mode
            if data.json_file_path:
                output["json_file_path"] = data.json_file_path
            if data.sqlite_path:
                output["sqlite_path"] = data.sqlite_path
            if data.sqlite_table:
                output["sqlite_table"] = data.sqlite_table
            if data.write_mode:
                output["write_mode"] = data.write_mode
            if isinstance(data.dedupe_keys, list):
                output["dedupe_keys"] = [key for key in data.dedupe_keys if isinstance(key, str) and key.strip()]
            batch_size = _coerce_limit(data.batch_size)
            if batch_size is not None:
                output["batch_size"] = batch_size
    edges = [
        {
            "id": edge.id,
            "source": edge.source,
            "target": edge.target,
            "branch": edge.branch,
            "label": edge.label,
            "order": edge.order,
        }
        for edge in graph.edges
    ]

    return ExecutionPlan(
        entry_url=entry_url,
        node_types=node_types,
        item_selector=item_selector,
        field_specs=field_specs,
        pagination=pagination,
        output=output,
        limits=limits,
        edges=edges,
        conditions=conditions,
    )


def execution_plan_to_dict(plan: ExecutionPlan) -> dict[str, Any]:
    return asdict(plan)
