"""Traversal helpers for workflow executor orchestration."""

from __future__ import annotations

from collections import deque

from backend.workflow.graph import build_adjacency_map, find_node_by_id, get_prerequisite_nodes


def collect_prerequisites(graph, node_id: str):
    adj_map = build_adjacency_map(graph)
    return get_prerequisite_nodes(graph, node_id, adj_map)


def create_subflow_queue(entry_node_id: str, boundary_start_node: str | None = None):
    start_node_id = boundary_start_node or entry_node_id
    return deque([start_node_id])


def get_subflow_adjacency_map(graph):
    return build_adjacency_map(graph)


def pop_next_subflow_node(graph, pending_nodes):
    node_id = pending_nodes.popleft()
    return node_id, find_node_by_id(graph, node_id)


def enqueue_successors(pending_nodes, adjacency_map, node_id: str, boundary_end_node: str | None = None):
    enqueued = []
    successors = adjacency_map.get(node_id, [])

    # Check for end marker set by handle_end
    # The orchestration loop will stop before calling this if ended is True,
    # but we guard here as a secondary check.
    for next_node_id in successors:
        if boundary_end_node and next_node_id == boundary_end_node:
            continue
        pending_nodes.append(next_node_id)
        enqueued.append(next_node_id)
    return enqueued
