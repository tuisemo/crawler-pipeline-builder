"""Workflow graph validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.workflow.schemas import (
    LegacyFieldAliasError,
    ValidateWorkflowRequest,
    WorkflowGraph,
    WorkflowNode,
    normalize_field_payload,
)


@dataclass
class WorkflowValidationError(Exception):
    """Raised when workflow validation fails."""

    error_code: str
    error: str

    def __str__(self):
        return f"{self.error_code}: {self.error}"


SUPPORTED_EXECUTABLE_NODE_TYPES = {
    "open_page",
    "select_list",
    "extract_field",
    "paginate",
    "emit_record",
    "loop",
    "condition",
    "end",
}


def _find_duplicates(values) -> list[str]:
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _validate_field_schema(raw_field: object, index: int) -> None:
    try:
        normalized = normalize_field_payload(raw_field)
    except LegacyFieldAliasError as e:
        raise WorkflowValidationError(
            error_code="extract_field_legacy_aliases_not_supported",
            error=str(e),
        ) from e
    except Exception as e:
        raise WorkflowValidationError(
            error_code="extract_field_invalid_field",
            error=f"extract_field field[{index}] validation failed: {e}.",
        ) from e

    if not normalized.get("name"):
        raise WorkflowValidationError(
            error_code="extract_field_requires_field_name",
            error=f"extract_field field[{index}] requires a non-empty name.",
        )
    if not normalized.get("selector"):
        raise WorkflowValidationError(
            error_code="extract_field_requires_field_selector",
            error=f"extract_field field[{index}] requires a non-empty selector.",
        )


def _validate_edge_references(graph: WorkflowGraph) -> None:
    node_ids = {node.id for node in graph.nodes}
    missing_sources = sorted({edge.source for edge in graph.edges if edge.source not in node_ids})
    if missing_sources:
        raise WorkflowValidationError(
            error_code="edge_source_missing",
            error=f"Workflow edges reference missing source nodes: {', '.join(missing_sources)}.",
        )

    missing_targets = sorted({edge.target for edge in graph.edges if edge.target not in node_ids})
    if missing_targets:
        raise WorkflowValidationError(
            error_code="edge_target_missing",
            error=f"Workflow edges reference missing target nodes: {', '.join(missing_targets)}.",
        )


def _validate_supported_node_types(nodes: Iterable[WorkflowNode]) -> None:
    unsupported = sorted({node.type for node in nodes if node.type not in SUPPORTED_EXECUTABLE_NODE_TYPES})
    if unsupported:
        raise WorkflowValidationError(
            error_code="unsupported_node_type",
            error=f"Workflow contains unsupported node types for execution: {', '.join(unsupported)}.",
        )


def validate_node_data(node: WorkflowNode) -> None:
    """Validate required fields for a supported workflow node type."""
    node_type = node.type
    data = node.data

    if node_type == "open_page":
        if not (data.url and data.url.strip()):
            raise WorkflowValidationError(
                error_code="open_page_requires_url",
                error="open_page node requires a non-empty url field.",
            )
    elif node_type == "select_list":
        if not (data.item_selector and data.item_selector.strip()):
            raise WorkflowValidationError(
                error_code="select_list_requires_item_selector",
                error="select_list node requires a non-empty item_selector field.",
            )
    elif node_type == "extract_field":
        raw_fields = data.fields
        if not raw_fields:
            raise WorkflowValidationError(
                error_code="extract_field_requires_fields",
                error="extract_field node requires a non-empty fields list.",
            )
        if not isinstance(raw_fields, list):
            raise WorkflowValidationError(
                error_code="extract_field_requires_fields_list",
                error="extract_field node fields must be a list.",
            )
        if len(raw_fields) == 0:
            raise WorkflowValidationError(
                error_code="extract_field_requires_fields",
                error="extract_field node requires at least one field.",
            )
        for i, raw_field in enumerate(raw_fields):
            _validate_field_schema(raw_field, i)
    elif node_type == "paginate":
        if not (data.pagination_selector and data.pagination_selector.strip()):
            raise WorkflowValidationError(
                error_code="paginate_requires_pagination_selector",
                error="paginate node requires a non-empty pagination_selector field.",
            )
    elif node_type == "condition":
        if not (data.condition and data.condition.strip()):
            raise WorkflowValidationError(
                error_code="condition_requires_expression",
                error="condition node requires a non-empty condition field.",
            )


def validate_graph(request: ValidateWorkflowRequest) -> dict:
    """Validate a workflow graph and return a domain result."""
    graph = request.graph
    if not graph.nodes:
        raise WorkflowValidationError(
            error_code="workflow_empty",
            error="Workflow must have at least one node.",
        )

    duplicate_node_ids = _find_duplicates(node.id for node in graph.nodes)
    if duplicate_node_ids:
        raise WorkflowValidationError(
            error_code="duplicate_node_ids",
            error=f"Workflow node ids must be unique: {', '.join(duplicate_node_ids)}.",
        )

    duplicate_edge_ids = _find_duplicates(edge.id for edge in graph.edges)
    if duplicate_edge_ids:
        raise WorkflowValidationError(
            error_code="duplicate_edge_ids",
            error=f"Workflow edge ids must be unique: {', '.join(duplicate_edge_ids)}.",
        )

    _validate_edge_references(graph)
    _validate_supported_node_types(graph.nodes)

    entry_nodes = [node for node in graph.nodes if node.type == "open_page"]
    if not entry_nodes:
        raise WorkflowValidationError(
            error_code="entry_node_missing",
            error="Workflow must have an 'open_page' entry node.",
        )
    if len(entry_nodes) > 1:
        raise WorkflowValidationError(
            error_code="entry_node_multiple",
            error="Workflow can only have one 'open_page' entry node.",
        )

    for node in graph.nodes:
        validate_node_data(node)

    return {"success": True, "message": "Workflow is valid"}
