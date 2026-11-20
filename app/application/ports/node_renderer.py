"""Rendering of a source node for people to read."""

from abc import ABC, abstractmethod

from app.domain.documents.node import Node


class NodeRenderer(ABC):
    @abstractmethod
    def render(self, node: Node, document_title: str) -> str: ...
