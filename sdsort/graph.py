from __future__ import annotations

from collections import defaultdict
from typing import Generic, TypeAlias, TypeVar

from .block import Block

B = TypeVar("B", bound=Block)

Edges: TypeAlias = dict[B, list[B]]


class AcyclicGraph(Generic[B]):
    def __init__(self) -> None:
        self._edges: Edges[B] = defaultdict(list)

    def add_edge(self, *, _from: B, to: B) -> bool:
        if to in self._edges[_from]:
            return False
        if _from == to or self._is_reachable(_from, start=to):
            return False
        self._edges[_from].append(to)
        return True

    def _is_reachable(self, target: B, *, start: B) -> bool:
        visited = set[B]()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(self._edges[node])
        return False

    @property
    def edges(self) -> Edges[B]:
        return self._edges
