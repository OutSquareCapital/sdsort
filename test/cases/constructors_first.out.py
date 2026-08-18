from collections.abc import Callable


def mark(method: Callable[..., object]) -> Callable[..., object]:
    return method


class Service:
    def __new__(cls):
        return super().__new__(cls)

    @mark
    def __init__(self):
        pass

    @mark
    def __post_init__(self):
        self._initialize()

    @mark
    def public_api(self):
        self.public_helper()

    def public_helper(self):
        pass

    @mark
    def _initialize(self):
        pass
