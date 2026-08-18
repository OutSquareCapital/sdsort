from __future__ import annotations

import ast
from ast import parse
from io import BytesIO
from pathlib import Path
from tokenize import COMMENT, tokenize
from typing import Literal, TypeAlias, TypeVar

from . import strategies
from .block import Block
from .context import Context, gather_context
from .format import normalize_blank_lines
from .utils.ast import find_start_of_class_body, get_class_nodes
from .utils.file import read_file, split_lines

ResultType: TypeAlias = (
    tuple[Literal["sorted"], str] | tuple[Literal["skipped"], None] | tuple[Literal["unchanged"], None]
)
MODULE_SORTER = strategies.build_pipeline(strategies.steps_for_module(), early_return=True)
A = TypeVar("A", bound=ast.AST)
B = TypeVar("B", bound=Block)


def step_down_sort(python_file_path: Path) -> ResultType:
    source = read_file(python_file_path)
    if _should_skip(source):
        return ("skipped", None)

    syntax_tree = parse(source, filename=python_file_path)
    context = gather_context(syntax_tree, Path(python_file_path).resolve())
    source_lines = split_lines(source)
    sorted_lines = _sort_source(source_lines, syntax_tree, context)

    if source_lines != sorted_lines:
        return ("sorted", normalize_blank_lines(sorted_lines))
    else:
        return ("unchanged", None)


def _sort_source(source_lines: list[str], syntax_tree: ast.Module, context: Context) -> list[str]:
    # First, sort top-level blocks (functions and classes)
    modified_lines = MODULE_SORTER(syntax_tree, source_lines, context, 0)
    final_lines: list[str] = []
    methods_sorter = strategies.build_pipeline(strategies.steps_for_methods(context))
    # Then, sort methods within classes
    for cls in get_class_nodes(_modified_tree(modified_lines, source_lines, syntax_tree)):
        # Copy everything, which hasn't been copied so far, up until the class body,
        class_body_start = find_start_of_class_body(cls, modified_lines)
        final_lines.extend(modified_lines[len(final_lines) : class_body_start])
        # Copy class after sorting its methods
        final_lines.extend(methods_sorter(cls, modified_lines, context, class_body_start))
    # Copy remainder of file
    final_lines.extend(modified_lines[len(final_lines) :])
    return final_lines


def _modified_tree(modified_lines: list[str], source_lines: list[str], syntax_tree: ast.Module) -> ast.Module:
    if modified_lines == source_lines:
        # Nothing moved, so every line number still holds and the original tree remains valid.
        return syntax_tree
    else:
        # Re-parse to get updated line numbers for class sorting
        return parse("\n".join(modified_lines) + "\n")


def _should_skip(source: str) -> bool:
    # Tokenizing is expensive, so first do a cheap test
    if "sdsort" not in source:
        return False

    code_bytes = BytesIO(source.encode("utf-8"))
    for token in tokenize(code_bytes.readline):
        if token.type == COMMENT:
            key, _, value = token.string.lstrip("#").partition(":")
            if key.strip() == "sdsort" and value.strip() == "skip_file":
                return True
    return False
