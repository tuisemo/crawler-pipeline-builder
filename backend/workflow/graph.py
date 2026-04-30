"""Graph traversal helpers for workflow executor.

Separated from workflow_executor.py to reduce coupling between
graph traversal algorithms and node execution logic.
"""

from collections import deque
from typing import Dict, List, Optional, Tuple

from backend.workflow.schemas import WorkflowGraph, WorkflowNode


def build_node_map(graph: WorkflowGraph) -> Dict[str, WorkflowNode]:
    """Build a map from node ID to node."""
    return {node.id: node for node in graph.nodes}


def build_adjacency_map(graph: WorkflowGraph) -> Dict[str, List[str]]:
    """Build adjacency map for graph traversal."""
    adj = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.source in adj:
            adj[edge.source].append(edge.target)
    return adj


def find_entry_node(graph: WorkflowGraph) -> Optional[WorkflowNode]:
    """Find the open_page entry node."""
    for node in graph.nodes:
        if node.type == "open_page":
            return node
    return None


def find_node_by_id(graph: WorkflowGraph, node_id: str) -> Optional[WorkflowNode]:
    """Find a node by ID."""
    for node in graph.nodes:
        if node.id == node_id:
            return node
    return None


def get_prerequisite_nodes(
    graph: WorkflowGraph, node_id: str, adj_map: Dict[str, List[str]]
) -> List[WorkflowNode]:
    """Return prerequisite nodes in execution order from entry to target.

    Uses BFS to find the shortest path from entry node to the target node,
    returning the nodes along that path (excluding the target itself).
    """
    entry_node = find_entry_node(graph)
    if not entry_node or entry_node.id == node_id:
        return []

    node_map = build_node_map(graph)
    queue = deque([(entry_node.id, [entry_node])])
    visited = set()

    while queue:
        current_id, path = queue.popleft()
        if current_id in visited:
            continue
        visited.add(current_id)

        for next_id in adj_map.get(current_id, []):
            next_node = node_map.get(next_id)
            if not next_node or next_node.type == "end":
                continue

            next_path = path + [next_node]
            if next_id == node_id:
                return path

            queue.append((next_id, next_path))

    return []
