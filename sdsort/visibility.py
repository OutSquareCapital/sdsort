from __future__ import annotations

import ast
from collections.abc import MutableMapping
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Final, Generic, TypeAlias, TypeVar

if TYPE_CHECKING:
    from collections.abc import Container, Iterable

    from sdsort.context import TomlTable

T = TypeVar("T", bound=int | None)


@dataclass(slots=True)
class VisibilityRanks(Generic[T]):
    """Configuration options for sorting logic based on visibility of method names on a given class.\\
        We use a TypeState pattern to avoid code duplication and ensure that the consumers of this class handle the expected state of the ranks."""

    inner: Final[RanksData[T]]

    @classmethod
    def from_kwargs(cls, **kwargs: int | None) -> VisibilityRanks[int | None]:
        """Convenience helper for testing purposes."""

        iterator = ((k, kwargs.get(k.name.lower())) for k in MethodVisibility)
        return VisibilityRanks(dict(iterator))

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
            return VisibilityRanks(dict(zip(MethodVisibility, values)))

    def into_ok_or_default(self: VisibilityRanks[int | None]) -> VisibilityRanks[int]:
        """Transform a `VisibilityRanks[T]` into a `VisibilityRanks[int]` by replacing `None` values by a default value.\\
        The default value is the maximum of the non-`None` ranks plus one, so that any `None` rank is considered to be "after" all the other ranks."""
        default = max(rank for rank in self.inner.values() if rank is not None) + 1
        # In-place mutation for efficiency. We can statically guarantee the type output after this operation.
        for k, rank in self.inner.items():
            if rank is None:
                self.inner[k] = default
        return self  # pyright: ignore[reportArgumentType, reportReturnType]

    def classify_for_block(self: VisibilityRanks[int], name: str) -> int:
        """Classify a `FunctionBlock` according to its name and assign it the corresponding rank."""
        return self.inner[MethodVisibility.new(name)]


@dataclass(slots=True)
class MethodInfos:
    visibility: MethodVisibility
    behavior: MethodBehavior
    contract: MethodContract

    @classmethod
    def from_node(cls, node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfos:
        """Create a `MethodInfos` instance from an AST node representing a function definition."""
        decorators_names = tuple(
            decorator.id for decorator in node.decorator_list if isinstance(decorator, ast.Name)
        )
        visibility = MethodVisibility.new(node.name)
        behavior = MethodBehavior.new(decorators_names)
        contract = MethodContract.new(decorators_names)
        return MethodInfos(visibility, behavior, contract)


class MethodBehavior(StrEnum):
    """Mutually exclusive decorators that define the behavior of a method."""

    STATICMETHOD = auto()
    CLASSMETHOD = auto()
    PROPERTY = auto()
    INSTANCEMETHOD = auto()

    @classmethod
    def new(cls, names: Iterable[str]) -> MethodBehavior:
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
    ABSTRACT_OVERRIDE = auto()
    """When a method stack both the `@abstractmethod` and `@override` decorators, it is considered to be an abstract override."""
    NONE = auto()
    """None of the above decorators are present on the method."""

    @classmethod
    def new(cls, names: Container[str]) -> MethodContract:
        match cls.OVERRIDE in names, cls.ABSTRACT in names:
            case False, False:
                return cls.NONE
            case False, True:
                return cls.ABSTRACT
            case True, False:
                return cls.OVERRIDE
            case True, True:
                return cls.ABSTRACT_OVERRIDE


class MethodVisibility(StrEnum):
    """Mutually exclusive visibility levels for a given method."""

    DUNDER = auto()
    """A method name that starts and ends with double underscores (e.g. `__init__`)."""
    PRIVATE = auto()
    """A method name with same prefix as a dunder, but no suffix (e.g. `__private`)."""
    PROTECTED = auto()
    """A method name that starts with a single underscore (e.g. `_protected`)."""
    PUBLIC = auto()
    """Any method with no naming pattern corresponding to the above (e.g. `public`)."""

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


RanksData: TypeAlias = MutableMapping[MethodVisibility, T]
"""Inner data structure for `VisibilityRanks`."""
