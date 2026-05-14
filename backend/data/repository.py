from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class Repository:
    @property
    def events(self):
        return import_module("data.sqlite.events")

    @property
    def feedback(self):
        return import_module("data.feedback")

    @property
    def graph(self):
        return import_module("data.graph.connection")

    @property
    def leads(self):
        return import_module("data.sqlite.leads")

    @property
    def profile(self):
        return import_module("data.graph.profile")

    @property
    def settings(self):
        return import_module("data.sqlite.settings")

    @property
    def vector(self):
        return import_module("data.vector.connection")


def create_repository() -> Repository:
    return Repository()
