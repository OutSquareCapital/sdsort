from __future__ import annotations

from collections.abc import Container, Iterable, MutableMapping
from enum import Enum, StrEnum, auto
from typing import TYPE_CHECKING, Literal, Self, TypeAlias, TypeVar

if TYPE_CHECKING:
    from sdsort.context import TomlTable

T = TypeVar("T", bound=int | None)
K = TypeVar("K", bound=Enum)


Names = Literal["visibility", "behavior", "contract", "alphabetical"]
"""Type alias for the names of the rules that can be applied when sorting methods."""


Config: TypeAlias = MutableMapping[K, int]
"""Inner data structure for `VisibilityRanks`."""


class _Rule(StrEnum):
    @classmethod
    def as_config(cls, **kwargs: int | None) -> Config[Self]:
        """Convenience helper for testing purposes."""

        iterator = ((k, kwargs.get(k.name.lower())) for k in cls)
        return _into_config(iterator)

    @classmethod
    def try_into(cls, config: TomlTable) -> Config[Self] | None:
        """Try to create a `Config` instance corresponding to this rule from an opaque dictionary.

        Args:
            config (TomlTable): A configuration dictionary, parsed from a TOML file, which may contain the needed keys for instantiation.

        Returns:
            Config[Self, int | None] | None: A `Config` instance if the configuration is valid, otherwise `None`.
        """
        values = tuple(config.get(k) for k in cls)
        if all(value is None for value in values):
            return None
        else:
            return _into_config(zip(cls, values))


def _into_config(iterable: Iterable[tuple[K, int | None]]) -> Config[K]:
    """Transform an  `Iterable[tuple[K, V]]`, where `K: Enum`, into a `Config[K]` dictionary by replacing `None` values by a default value.\\
    Said default value is the maximum of the non-`None` ranks plus one, so that any `None` value is considered to be **after** all the other ranks."""
    config = dict(iterable)
    default = max(rank for rank in config.values() if rank is not None) + 1
    # In-place mutation for efficiency. We can statically guarantee the type output after this operation.
    for k, rank in config.items():
        if rank is None:
            config[k] = default
    return config  # pyright: ignore[reportArgumentType, reportReturnType]


class Behavior(_Rule):
    """Mutually exclusive decorators that define the behavior of a method."""

    STATICMETHOD = auto()
    """@staticmethod."""
    CLASSMETHOD = auto()
    """@classmethod."""
    PROPERTY = auto()
    """@property."""
    INSTANCEMETHOD = auto()
    """Any method without a decorator corresponding to the above (e.g. `def method(self): ...`)."""

    @classmethod
    def new(cls, names: Iterable[str]) -> Behavior:
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


class Contract(_Rule):
    """Defines the contract of a method, i.e. whether it's an interface, an implementation of an interface, or unrelated to a class hierarchy.\\
    The contract is determined by the presence (or complete absence) of specific decorators."""

    ABSTRACTMETHOD = auto()
    """Correspond to `@abc.abstractmethod` decorator. Note that this decorator has runtime implications, which is not the case for it's counterpart `@override` decorator."""
    OVERRIDE = auto()
    """Correspond to `@typing.override` decorator."""
    ABSTRACT_OVERRIDE = auto()
    """When a method has both the `@abc.abstractmethod` and `@typing.override` decorators, it is considered to be an abstract override.\\
    Can be used in intermediate classes to narrow types, or share documentation."""
    NONE = auto()
    """None of the above decorators are present on the method."""

    @classmethod
    def new(cls, names: Container[str]) -> Contract:
        match cls.OVERRIDE in names, cls.ABSTRACTMETHOD in names:
            case False, False:
                return cls.NONE
            case False, True:
                return cls.ABSTRACTMETHOD
            case True, False:
                return cls.OVERRIDE
            case True, True:
                return cls.ABSTRACT_OVERRIDE


class Visibility(_Rule):
    """Defines the visibility of a method based on its name, i.e is it intended to be public, or an implementation detail.\\
    The visibility is determined by the naming convention of the method."""

    DUNDER = auto()
    """A method name that starts and ends with double underscores (e.g. `__init__`)."""
    PRIVATE = auto()
    """A method name with same prefix as a dunder, but no suffix (e.g. `__private`)."""
    PROTECTED = auto()
    """A method name that starts with a single underscore (e.g. `_protected`)."""
    PUBLIC = auto()
    """Any method with no naming pattern corresponding to the above (e.g. `public`)."""

    @classmethod
    def new(cls, name: str) -> Visibility:
        if name.startswith("__"):
            if name.endswith("__"):
                return cls.DUNDER
            else:
                return cls.PRIVATE
        elif name.startswith("_"):
            return cls.PROTECTED
        else:
            return cls.PUBLIC
