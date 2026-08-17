from abc import abstractmethod

from typing_extensions import override


class Interface:
    @classmethod
    def class_override(cls):
        pass

    @staticmethod
    @abstractmethod
    def static_abstract_override():
        pass

    @staticmethod
    def static_override():
        pass


class Service(Interface):
    @staticmethod
    def static_plain():
        pass

    @classmethod
    @override
    def class_override(cls):
        pass

    @staticmethod
    @abstractmethod
    def static_abstract():
        pass

    @property
    def property_plain(self):
        pass

    @classmethod
    def class_plain(cls):
        pass

    def instance_plain(self):
        pass

    @staticmethod
    @abstractmethod
    @override
    def static_abstract_override():
        pass

    @staticmethod
    @override
    def static_override():
        pass
