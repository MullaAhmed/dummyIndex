"""Sample app module for dummyindex.context tests."""
from __future__ import annotations


class App:
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        return f"running {self.name}"


def make_app(name: str) -> App:
    return App(name)


def _private_helper() -> int:
    return 1
