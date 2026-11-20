from jinja2 import Environment, PackageLoader, select_autoescape

from app.application.ports.node_renderer import NodeRenderer
from app.domain.documents.node import Node

DEFAULT_TITLE = "Legal text"


class JinjaNodeRenderer(NodeRenderer):
    def __init__(self) -> None:
        self._environment = Environment(
            loader=PackageLoader("app.adapters.outbound.rendering", "templates"),
            autoescape=select_autoescape(("html", "xml")),
        )

    def render(self, node: Node, document_title: str) -> str:
        return self._environment.get_template("node.html").render(
            document_title=document_title or "",
            title=node.title or DEFAULT_TITLE,
            breadcrumbs=node.breadcrumbs or [],
            text=node.text or "",
            node_type=node.node_type,
        )
