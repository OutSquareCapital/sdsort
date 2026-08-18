from __future__ import annotations

import tomllib
from ast import ImportFrom, Module
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from itertools import takewhile
from typing import TYPE_CHECKING, Any, TypeVar

from sdsort import config

if TYPE_CHECKING:
    from pathlib import Path

    TomlTable = dict[str, Any]


T = TypeVar("T", bound=int | None)


class FileKind(StrEnum):
    """Enumeration of file kinds that sdsort can process."""

    PY = ".py"
    STUB = ".pyi"
    TOML = ".toml"

    def as_rglob(self) -> str:
        return f"**/*{self.value}*"

    def as_glob(self) -> str:
        return f"**/*{self.value}"


@dataclass
class Context:
    deferred_annotations: bool
    """Whether lazy annotations are enabled or not."""
    config: config.Config = field(default_factory=config.Config)
    sort_by_name: bool = False
    sort_by_dependency: bool = True
    constructors_first: bool = True


def gather_context(root_node: Module, file_path: Path | None = None) -> Context:
    table, deferred_annotations = _get_config_and_annotations(file_path, root_node)
    return Context(
        deferred_annotations,
        config.from_table(table),
        table.get(config.Options.METHOD_BY_NAME, False),
        table.get(config.Options.METHOD_BY_DEPENDENCY, True),
        table.get(config.Options.METHOD_CONSTRUCTORS_FIRST, True),
    )


def _get_config_and_annotations(file_path: Path | None, root_node: Module) -> tuple[TomlTable, bool]:
    match file_path:
        case None:
            return {}, _check_from_future_annotations(root_node)
        case path:
            match path.suffix:
                case FileKind.STUB:
                    return _handle_pyproject(path, True)
                case FileKind.PY:
                    return _handle_pyproject(path, _check_from_future_annotations(root_node))
                case _:
                    raise ValueError(f"Unsupported file extension: {path.suffix}")


def _check_from_future_annotations(root_node: Module) -> bool:
    imports = (statement for statement in root_node.body if isinstance(statement, ImportFrom))
    return any(
        imprt.module == "__future__" and any(alias.name == "annotations" for alias in imprt.names)
        for imprt in imports
    )


def _handle_pyproject(file_path: Path, deferred_annotations: bool) -> tuple[TomlTable, bool]:
    match _find_pyproject(file_path.parent):
        case None:
            return {}, deferred_annotations
        case pyproject:
            data = _load_pyproject(pyproject)
            config: TomlTable = data.get("tool", {}).get("sdsort", {})
            if not deferred_annotations:
                deferred_annotations = _targets_python314_or_newer(data)
            return config, deferred_annotations


@lru_cache
def _load_pyproject(pyproject: Path) -> TomlTable:
    with pyproject.open("rb") as f:
        return tomllib.load(f)


def _targets_python314_or_newer(data: TomlTable) -> bool:
    specifier: str = data.get("project", {}).get("requires-python", "")
    for part in specifier.split(","):
        part = part.strip()
        if part.startswith(">="):
            version = part[2:].strip().split(".")
            if len(version) >= 2:
                major = _leading_int(version[0])
                minor = _leading_int(version[1])
                if major == 3 and minor >= 14:
                    return True
    return False


def _leading_int(text: str) -> int:
    """Parse the leading integer of a version segment.

    PEP 440 permits pre-release specifiers in requires-python (e.g. ">=3.14a1"), so a
    segment like "14a1" must not be passed to int() directly. Returns 0 when there is
    no leading digit.
    """
    digits = "".join(takewhile(str.isdigit, text))
    return int(digits) if digits else 0


def _find_pyproject(directory: Path) -> Path | None:
    for parent in [directory, *directory.parents]:
        candidate = parent.joinpath("pyproject").with_suffix(FileKind.TOML)
        if candidate.is_file():
            return candidate
    return None
