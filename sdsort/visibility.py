from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sdsort.context import TomlTable

T = TypeVar("T", bound=int | None)


@dataclass(slots=True)
class VisibilityRanks(Generic[T]):
    """Configuration options for sorting logic based on visibility of method names on a given class.\\
        We use a TypeState pattern to avoid code duplication and ensure that the consumers of this class handle the expected state of the ranks."""

    dunder: T
    """A method name that starts and ends with double underscores (e.g. `__init__`)."""
    private: T
    """A method name with same prefix as a dunder, but no suffix (e.g. `__private`)."""
    protected: T
    """A method name that starts with a single underscore (e.g. `_protected`)."""
    public: T
    """Any method with no naming pattern corresponding to the above (e.g. `public`)."""

    @classmethod
    def try_from(cls, config: TomlTable) -> VisibilityRanks[int | None] | None:
        """Try to create a `VisibilityRanks` instance from a configuration dictionary.

        Args:
            config (TomlTable): A configuration dictionary, parsed from a TOML file, which may contain the needed keys for instantiation.

        Returns:
            VisibilityRanks[int | None] | None: A `VisibilityRanks` instance if the configuration is valid, otherwise `None`.
        """
        values = tuple(config.get(k) for k in MethodVisibility)
        if all(value is None for value in values):
            return None
        else:
            return VisibilityRanks(*values)

    def into_ok_or_default(self) -> VisibilityRanks[int]:
        """Transform a `VisibilityRanks[T]` into a `VisibilityRanks[int]` by replacing `None` values by a default value.\\
        The default value is the maximum of the non-`None` ranks plus one, so that any `None` rank is considered to be "after" all the other ranks."""
        ranks = (self.dunder, self.private, self.protected, self.public)
        default = max(rank for rank in ranks if rank is not None) + 1
        return VisibilityRanks[int](*(rank if rank is not None else default for rank in ranks))

    def classify_for_block(self: VisibilityRanks[int], name: str) -> int:
        """Classify a `FunctionBlock` according to its name and assign it the corresponding rank."""
        return MethodVisibility.new(name).get_rank(self)


@dataclass(slots=True)
class MethodInfos:
    visibility: MethodVisibility
    kind: LogicalKind
    override: bool
    abstract: bool

    @classmethod
    def from_node(cls, node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfos:
        """Create a `MethodInfos` instance from an AST node representing a function definition."""
        decorators_names = frozenset(
            decorator.id for decorator in node.decorator_list if isinstance(decorator, ast.Name)
        )
        visibility = MethodVisibility.new(node.name)
        kind = LogicalKind.new(decorators_names)
        override = MethodContract.OVERRIDE in decorators_names
        abstract = MethodContract.ABSTRACT in decorators_names
        return MethodInfos(visibility, kind, override, abstract)


class LogicalKind(StrEnum):
    """Mutually exclusive decorators that define the behavior of a method."""

    STATICMETHOD = auto()
    CLASSMETHOD = auto()
    PROPERTY = auto()
    INSTANCEMETHOD = auto()

    @classmethod
    def new(cls, names: Iterable[str]) -> LogicalKind:
        """Determine the logical kind of a method based on its decorators."""
        for name in names:
            match name:
                case cls.STATICMETHOD:
                    return cls.STATICMETHOD
                case cls.CLASSMETHOD:
                    return cls.CLASSMETHOD
                case cls.PROPERTY:
                    return cls.PROPERTY
                case _:
                    continue
        return cls.INSTANCEMETHOD


class MethodContract(StrEnum):
    """Potentially overlapping decorators that define the contract of a method."""

    ABSTRACT = auto()
    OVERRIDE = auto()


class MethodVisibility(StrEnum):
    """Mutually exclusive visibility levels for a given method."""

    DUNDER = auto()
    PRIVATE = auto()
    PROTECTED = auto()
    PUBLIC = auto()

    @classmethod
    def new(cls, name: str) -> MethodVisibility:
        if name.startswith("__"):
            if name.endswith("__"):
                return cls.DUNDER
            else:
                return cls.PRIVATE
        elif name.startswith("_"):
            return cls.PROTECTED
        else:
            return cls.PUBLIC

    def get_rank(self, ranks: VisibilityRanks[int]) -> int:
        match self:
            case MethodVisibility.DUNDER:
                return ranks.dunder
            case MethodVisibility.PRIVATE:
                return ranks.private
            case MethodVisibility.PROTECTED:
                return ranks.protected
            case MethodVisibility.PUBLIC:
                return ranks.public
