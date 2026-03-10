"""Sample Python module for testing."""


def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


def decorator(func):
    """A simple decorator."""
    return func


@decorator
def decorated_function() -> None:
    """A decorated function."""
    pass


class Calculator:
    """A simple calculator."""

    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

    def divide(self, x: float, y: float) -> float:
        return x / y


class Outer:
    """An outer class with a nested class."""

    class Inner:
        """A nested inner class."""

        def inner_method(self) -> str:
            return "inner"


# Module-level constant — should NOT be extracted as a symbol
MY_CONSTANT = 42
