from __future__ import annotations

from abc import abstractmethod
from ast import Name
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sdsort.utils.ast import Function


class Rule(StrEnum):
    """Base class for all rules that can be applied when sorting methods.\\
    Each rule is represented by an enum value, and the order of the values defines the default sorting order when no configuration is provided."""

    @classmethod
    @abstractmethod
    def from_node(cls, node: Function) -> Self:
        """Determine the enum variant corresponding to the given `Function` AST node."""


class Behavior(Rule):
    """Mutually exclusive decorators that define the behavior of a method."""

    CLASSMETHOD = auto()
    """@classmethod."""
    STATICMETHOD = auto()
    """@staticmethod."""
    PROPERTY = auto()
    """@property."""
    INSTANCEMETHOD = auto()
    """Any method without a decorator corresponding to the above (e.g. `def method(self): ...`)."""

    @classmethod
    def from_node(cls, node: Function) -> Behavior:
        for name in _names_from_function(node):
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


class Contract(Rule):
    """Defines the contract of a method, i.e. whether it's an interface, an implementation of an interface, or unrelated to a class hierarchy.\\
    The contract is determined by the presence (or complete absence) of specific decorators."""

    ABSTRACTMETHOD = auto()
    """Correspond to `@abc.abstractmethod` decorator. Note that this decorator has runtime implications, which is not the case for it's counterpart `@override` decorator."""
    ABSTRACT_OVERRIDE = auto()
    """When a method has both the `@abc.abstractmethod` and `@typing.override` decorators, it is considered to be an abstract override.\\
    Can be used in intermediate classes to narrow types, or share documentation."""
    OVERRIDE = auto()
    """Correspond to `@typing.override` decorator."""
    NONE = auto()
    """None of the above decorators are present on the method."""

    @classmethod
    def from_node(cls, node: Function) -> Contract:
        is_override = False
        is_abstract = False
        for name in _names_from_function(node):
            match name:
                case cls.OVERRIDE:
                    is_override = True
                case cls.ABSTRACTMETHOD:
                    is_abstract = True
                case _:
                    continue
        match is_override, is_abstract:
            case False, False:
                return cls.NONE
            case False, True:
                return cls.ABSTRACTMETHOD
            case True, False:
                return cls.OVERRIDE
            case True, True:
                return cls.ABSTRACT_OVERRIDE


def _names_from_function(node: Function) -> Iterator[str]:
    return (decorator.id for decorator in node.decorator_list if isinstance(decorator, Name))


class Visibility(Rule):
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
    def from_node(cls, node: Function) -> Visibility:
        name = node.name
        if name.startswith("__"):
            if name.endswith("__"):
                return cls.DUNDER
            else:
                return cls.PRIVATE
        elif name.startswith("_"):
            return cls.PROTECTED
        else:
            return cls.PUBLIC
