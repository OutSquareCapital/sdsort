from collections.abc import Callable


def mark(method: Callable[..., object]) -> Callable[..., object]:
    return method


class Service:
    def public_helper(self):
        pass

    @mark
    def __post_init__(self):
        self._initialize()

    @mark
    def __init__(self):
        pass

    def __new__(cls):
        return super().__new__(cls)

    @mark
    def public_api(self):
        self.public_helper()

    @mark
    def _initialize(self):
        pass
