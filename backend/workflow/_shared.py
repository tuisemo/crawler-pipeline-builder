"""Shared internal helpers for workflow modules.

Not part of the public API; imported only by sibling workflow files.
"""

from __future__ import annotations

from backend.workflow.schemas import (
    NodeData,
    WorkflowGraph,
    WorkflowNode,
    normalize_field_payloads,
)


DEPRECATED_NODE_DATA_KEYS = {"max_steps", "max_items"}


def _sanitize_extract_fields(fields: list[dict] | None) -> list[dict] | None:
    return normalize_field_payloads(fields, assign_fallback_names=False)


def _sanitize_node_data(data: NodeData) -> NodeData:
    payload = data.model_dump()
    for key in DEPRECATED_NODE_DATA_KEYS:
        payload.pop(key, None)
    if isinstance(payload.get("fields"), list):
        payload["fields"] = _sanitize_extract_fields(payload.get("fields"))
    return NodeData.model_validate(payload)


def sanitize_graph(graph: WorkflowGraph) -> WorkflowGraph:
    """Strip deprecated keys from every node's data."""
    return WorkflowGraph(
        nodes=[
            WorkflowNode(id=node.id, type=node.type, data=_sanitize_node_data(node.data))
            for node in graph.nodes
        ],
        edges=list(graph.edges),
    )
