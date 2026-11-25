from uuid import uuid4

from app.adapters.outbound.persistence.repositories.sqlalchemy_node_repository import (
    _rows,
    stable_node_id,
)
from app.domain.documents.parsed_node import ParsedNode


def _node(path: str) -> ParsedNode:
    return ParsedNode("T", "text", ["Doc"], path, "section")


def test_node_ids_are_stable_per_document_and_path() -> None:
    document_id = uuid4()
    assert stable_node_id(document_id, "s1.a1") == stable_node_id(document_id, "s1.a1")
    assert stable_node_id(document_id, "s1.a1") != stable_node_id(document_id, "s1.a2")
    assert stable_node_id(document_id, "s1.a1") != stable_node_id(uuid4(), "s1.a1")


def test_repeated_paths_get_distinct_ids_that_survive_a_reparse() -> None:
    document_id = uuid4()
    nodes = [_node("n1"), _node("p1.h1_a"), _node("n1")]
    first = [row["id"] for row in _rows(document_id, nodes)]
    second = [row["id"] for row in _rows(document_id, nodes)]
    assert len(set(first)) == 3 and first == second
