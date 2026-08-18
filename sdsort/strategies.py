from __future__ import annotations

import ast
import itertools
from collections import defaultdict
from collections.abc import Callable, Collection, Hashable
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar

from .block import Block, FunctionBlock, block_for, resolve_overlapping_ranges
from .context import Context
from .graph import AcyclicGraph, Edges
from .rules import CONSTRUCTORS_DEFAULT, CONSTRUCTORS_RANKS
from .utils.ast import get_method_nodes, is_blank

if TYPE_CHECKING:
    from collections.abc import Sequence

    from _typeshed import SupportsRichComparison

A = TypeVar("A", bound=ast.AST)
B = TypeVar("B", bound=Block)
# Can't use pure typing constructs with old generics syntax. Replace Hashable with SupportsRichComparison once Python 3.11 support is dropped.
KeyFn: TypeAlias = Callable[[B], Hashable]
SortFn: TypeAlias = Callable[[list[B]], list[B]]
VisitFn: TypeAlias = Callable[[Edges[B], list[B], B], None]
RearrangeFn: TypeAlias = Callable[[list[str], Collection[B], list[B], int], list[str]]
BlockFindFn: TypeAlias = Callable[[A, list[str], Context], list[B]]
WalkFn: TypeAlias = Callable[[list[B], VisitFn[B], SortFn[B]], list[B]]
StepsFns: TypeAlias = tuple[BlockFindFn[A, B], SortFn[B], VisitFn[B], WalkFn[B], RearrangeFn[B]]
Pipeline: TypeAlias = Callable[[A, list[str], Context, int], list[str]]


def build_pipeline(steps: StepsFns[A, B], early_return: bool = False) -> Pipeline[A]:
    def pipeline(node: A, source_lines: list[str], context: Context, start: int) -> list[str]:
        block_finder, block_sorter, visitor, recursive_walker, rearranger = steps
        blocks = block_finder(node, source_lines, context)
        if early_return and not blocks:
            return source_lines
        else:
            sorted_blocks = recursive_walker(blocks, visitor, block_sorter)
            return rearranger(source_lines, blocks, sorted_blocks, start)

    return pipeline


def steps_for_module() -> StepsFns[ast.Module, Block]:
    return (_Find.top_level_blocks, _SortBy.none(False), _Visit.top_block, _Walk.visit_module, _RearrangeLines.all)


def steps_for_methods(context: Context) -> StepsFns[ast.ClassDef, FunctionBlock]:
    f = _Find.method_blocks
    match bool(context.config), context.sort_by_name, context.sort_by_dependency:
        case False, False, True:
            return (
                f,
                _SortBy.none(context.constructors_first),
                _Visit.method(),
                _Walk.sort_and_visit,
                _RearrangeLines.all,
            )
        case False, True, False:
            return (f, _SortBy.name(context.constructors_first), _Visit.none, _Walk.sort, _RearrangeLines.all)
        case False, True, True:
            return (
                f,
                _SortBy.name(context.constructors_first),
                _Visit.method(),
                _Walk.sort_and_visit,
                _RearrangeLines.all,
            )
        case True, False, False:
            return (f, _SortBy.key(context.constructors_first), _Visit.none, _Walk.sort, _RearrangeLines.all)
        case True, False, True:
            return (
                f,
                _SortBy.key(context.constructors_first),
                _Visit.method_by_partition(),
                _Walk.sort_and_visit,
                _RearrangeLines.all,
            )
        case True, True, False:
            return (
                f,
                _SortBy.key_and_name(context.constructors_first),
                _Visit.none,
                _Walk.sort,
                _RearrangeLines.by_partition,
            )
        case True, True, True:
            return (
                f,
                _SortBy.key_and_name(context.constructors_first),
                _Visit.method_by_partition_and_name(),
                _Walk.sort_and_visit,
                _RearrangeLines.by_partition,
            )
        case False, False, False:
            raise ValueError("sdsort could not resolve a sorting strategy, as no options were active.")


class _SortBy:
    @staticmethod
    def none(constructors_first: bool) -> SortFn[Any]:
        return _make_sorter(lambda _: (), constructors_first)

    @staticmethod
    def name(constructors_first: bool) -> SortFn[FunctionBlock]:
        return _make_sorter(lambda method: method.name, constructors_first)

    @staticmethod
    def key(constructors_first: bool) -> SortFn[FunctionBlock]:
        return _make_sorter(lambda method: method.key, constructors_first)

    @staticmethod
    def key_and_name(constructors_first: bool) -> SortFn[FunctionBlock]:
        return _make_sorter(lambda method: (method.key, method.name), constructors_first)


def _make_sorter(
    sort_key: Callable[[FunctionBlock], SupportsRichComparison], constructors_first: bool
) -> SortFn[FunctionBlock]:
    def inner(method: FunctionBlock) -> SupportsRichComparison:
        return (CONSTRUCTORS_RANKS.get(method.name, CONSTRUCTORS_DEFAULT), sort_key(method))

    key = inner if constructors_first else sort_key
    return lambda blocks: sorted(blocks, key=key)


class _Visit:
    @staticmethod
    def none(edges: Edges[B], sorted_blocks: list[B], block: B) -> None:
        pass

    @staticmethod
    def top_block(edges: Edges[B], sorted_blocks: list[B], block: B) -> None:
        _move_current_block(sorted_blocks, block)
        for dependency in edges[block]:
            _Visit.top_block(edges, sorted_blocks, dependency)

    @staticmethod
    def method() -> VisitFn[B]:
        path: list[B] = []

        def inner(edges: Edges[B], sorted_blocks: list[B], block: B) -> None:
            path.append(block)
            _move_current_block(sorted_blocks, block)
            filtered = (s for s in edges[block] if s not in path)
            for dependency in filtered:
                inner(edges, sorted_blocks, dependency)
            path.pop()

        return inner

    @staticmethod
    def method_by_partition() -> VisitFn[FunctionBlock]:
        path: list[FunctionBlock] = []

        def inner(edges: Edges[FunctionBlock], sorted_blocks: list[FunctionBlock], block: FunctionBlock) -> None:
            path.append(block)
            _move_current_block(sorted_blocks, block)
            filtered = (s for s in edges[block] if s not in path and s.key == block.key)
            for dependency in filtered:
                inner(edges, sorted_blocks, dependency)
            path.pop()

        return inner

    @staticmethod
    def method_by_partition_and_name() -> VisitFn[FunctionBlock]:
        seen = set[FunctionBlock]()
        path: list[FunctionBlock] = []

        def inner(edges: Edges[FunctionBlock], sorted_blocks: list[FunctionBlock], block: FunctionBlock) -> None:
            if block in seen:
                return
            else:
                seen.add(block)
                path.append(block)
                _move_current_block(sorted_blocks, block)
                filtered = (s for s in edges[block] if s not in path and s.key == block.key and s not in seen)
                for dependency in filtered:
                    inner(edges, sorted_blocks, dependency)
                path.pop()

        return inner


def _move_current_block(blocks: list[B], block: B) -> None:
    # Move the current block last
    try:
        blocks.remove(block)
    except ValueError:
        pass
    blocks.append(block)


class _Find:
    @staticmethod
    def top_level_blocks(syntax_tree: ast.Module, source_lines: list[str], context: Context) -> list[Block]:
        blocks: list[Block] = []
        current_block: Block | None = None
        for node in syntax_tree.body:
            if current_block is None or not current_block.append(node):
                current_block = block_for(node, source_lines, context)
                blocks.append(current_block)

        resolve_overlapping_ranges(blocks)
        return blocks

    @staticmethod
    def method_blocks(node: ast.ClassDef, source_lines: list[str], context: Context) -> list[FunctionBlock]:
        method_nodes = get_method_nodes(node)
        methods: list[FunctionBlock] = []
        current_block: Block | None = None
        for method_node in method_nodes:
            if current_block is None or not current_block.append(method_node):
                current_block = FunctionBlock(method_node, source_lines, context)
                methods.append(current_block)
        resolve_overlapping_ranges(methods)
        return methods


class _RearrangeLines:
    @staticmethod
    def all(
        source_lines: list[str], original_blocks: Collection[B], sorted_blocks: list[B], start: int = 0
    ) -> list[str]:
        """Copy lines from the original source, shifting the methods/functions around as needed."""

        def lines_of(block: B) -> list[str]:
            return source_lines[block.start : block.end]

        result: list[str] = []
        pos = start
        sort_idx = 0

        for orig_block in original_blocks:
            result.extend(source_lines[pos : orig_block.start])  # filler is always emitted in original order
            pos = orig_block.end

            if sort_idx >= len(sorted_blocks) or orig_block != sorted_blocks[sort_idx]:
                # The next sorted block hasn't reached its trigger slot yet; skip this slot.
                # Blocks emitted early by the while-loop below also land here.
                continue

            result.extend(lines_of(sorted_blocks[sort_idx]))
            sort_idx += 1

            # A block that originally appeared before this slot should follow it immediately,
            # because its own slot was already passed (and skipped) earlier in the walk.
            while sort_idx < len(sorted_blocks) and sorted_blocks[sort_idx].start < orig_block.start:
                result.extend(lines_of(sorted_blocks[sort_idx]))
                sort_idx += 1
        return _finalize_rearranged_lines(source_lines, result, start, pos)

    @staticmethod
    def by_partition(
        source_lines: list[str], original_blocks: Collection[B], sorted_blocks: list[B], start: int = 0
    ) -> list[str]:
        def lines_of(block: Block) -> list[str]:
            return source_lines[block.start : block.end]

        result: list[str] = []
        pos = start
        sort_idx = 0
        blocks_by_start: dict[int, Block] = {}
        stop = start
        for block in original_blocks:
            blocks_by_start[block.start] = block
            stop = max(stop, block.end)
        while pos < stop:
            block = blocks_by_start.get(pos)
            if block is None:
                result.append(source_lines[pos])
                pos += 1
                continue
            result.extend(lines_of(sorted_blocks[sort_idx]))
            sort_idx += 1
            pos = block.end
        return _finalize_rearranged_lines(source_lines, result, start, pos)


def _finalize_rearranged_lines(source_lines: Sequence[str], result: list[str], start: int, pos: int) -> list[str]:
    if start == 0:
        # Include trailing content if we are doing the whole file
        result.extend(source_lines[pos:])

    result = _ensure_number_of_leading_blank_lines_remains_unchanged(
        source_lines[start : start + len(result)], result
    )
    return result


def _ensure_number_of_leading_blank_lines_remains_unchanged(
    original_lines: Collection[str],
    rearranged_lines: list[str],
) -> list[str]:
    assert len(original_lines) == len(rearranged_lines)
    num_leading_blanks_before = 0
    for _ in itertools.takewhile(is_blank, original_lines):
        num_leading_blanks_before += 1
    num_leading_blanks_after = 0
    for _ in itertools.takewhile(is_blank, rearranged_lines):
        num_leading_blanks_after += 1
    if num_leading_blanks_after > num_leading_blanks_before:
        # We have additional leading blanks.
        # Move them to the back and let the formatter take care of the rest.
        diff = num_leading_blanks_after - num_leading_blanks_before
        return list(rearranged_lines[diff:]) + [""] * diff
    return rearranged_lines


class _Walk:
    @staticmethod
    def sort(blocks: list[B], _visit_fn: VisitFn[B], sort_fn: SortFn[B]) -> list[B]:
        return sort_fn(blocks)

    @staticmethod
    def visit_module(blocks: list[B], visit_fn: VisitFn[B], _: SortFn[B]) -> list[B]:
        return _find_dependencies(blocks, visit_fn, _CallTarget.function)

    @staticmethod
    def visit_class(blocks: list[B], visit_fn: VisitFn[B], _: SortFn[B]) -> list[B]:
        return _find_dependencies(blocks, visit_fn, _CallTarget.method)

    @staticmethod
    def sort_and_visit(blocks: list[B], visit_fn: VisitFn[B], sort_fn: SortFn[B]) -> list[B]:
        return _find_dependencies(sort_fn(blocks), visit_fn, _CallTarget.method)


def _find_dependencies(
    blocks: list[B], visit_fn: VisitFn[B], get_call_target: Callable[[ast.Call], str | None]
) -> list[B]:
    dependencies = AcyclicGraph[B]()

    blocks_by_name: dict[str, list[B]] = defaultdict(list)
    for block in blocks:
        for name in block.names:
            blocks_by_name[name].append(block)

    for block in blocks:
        for name in block.find_predecessors():
            # XXX: filter out built-ins (e.g. str, int)?
            for predecessor_block in blocks_by_name.get(name, []):
                dependencies.add_edge(_from=predecessor_block, to=block)

    for block in blocks:
        for call in block.find_calls():
            target = get_call_target(call)
            if target is not None:
                for successor_block in blocks_by_name.get(target, []):
                    if isinstance(successor_block, FunctionBlock) and not successor_block.is_pytest_fixture:
                        dependencies.add_edge(_from=block, to=successor_block)
    edges = dependencies.edges
    sorted_blocks: list[B] = []
    for block in blocks:
        visit_fn(edges, sorted_blocks, block)
    return sorted_blocks


class _CallTarget:
    @staticmethod
    def method(node: ast.Call) -> str | None:
        """Extract target name from self.method() calls."""
        return (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            else None
        )

    @staticmethod
    def function(node: ast.Call) -> str | None:
        """Extract target name from direct function() calls."""
        return node.func.id if isinstance(node.func, ast.Name) else None
