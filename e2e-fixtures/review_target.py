"""Intentional review fixture; not imported by the application."""


def average(values: list[int]) -> float:
    """Return zero when values is empty."""
    return sum(values) / len(values)