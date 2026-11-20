"""Adds the complete parent article for questions that ask for a list."""

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.persistence.models.node_model import NodeModel
from app.adapters.outbound.retrieval.article_context_loader import ArticleContextLoader
from app.adapters.outbound.retrieval.ranked_candidate import RankedCandidate
from app.domain.documents.node_type import NodeType

LIST_QUESTION = re.compile(
    r"\b(?:какие|перечисл(?:и|ите)|список|перечень|основани[ея]|все\s+основания)\b",
    re.IGNORECASE,
)
SEED_COUNT = 10
EXPANDED_SCORE = 1.0
PART_TYPES = (NodeType.ARTICLE_SECTION.value, NodeType.ARTICLE_PART.value)


def asks_for_list(query: str) -> bool:
    return bool(LIST_QUESTION.search(query))


class ListQuestionExpander:
    """A single top paragraph rarely answers "which grounds…"; the whole article does."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def expand(self, ranked: list[tuple[str, RankedCandidate]]) -> dict[str, RankedCandidate]:
        """Return the first leading article as an extra top-scored candidate (or nothing)."""
        seed_ids = _seed_ids(ranked)
        seeds = await self._article_seeds(seed_ids)
        loader = ArticleContextLoader(self._session)
        for node_id in seed_ids:
            if node_id not in seeds:
                continue
            document_id, article_path = seeds[node_id]
            context = await loader.load(document_id, article_path)
            if context:
                text, node_ids = context
                key = f"article:{document_id}:{article_path}"
                return {key: RankedCandidate(text, node_ids, EXPANDED_SCORE)}
        return {}

    async def _article_seeds(self, seed_ids: list[UUID]) -> dict[UUID, tuple[UUID, str]]:
        if not seed_ids:
            return {}
        statement = select(
            NodeModel.id, NodeModel.document_id, NodeModel.path, NodeModel.node_type
        ).where(
            NodeModel.id.in_(seed_ids), NodeModel.node_type.in_(tuple(NodeType.article_family()))
        )
        rows = (await self._session.execute(statement)).all()
        return {row[0]: (row[1], _article_path(str(row[2]), row[3])) for row in rows if row[2]}


def _seed_ids(ranked: list[tuple[str, RankedCandidate]]) -> list[UUID]:
    keys = [key.removeprefix("node:") for key, _ in ranked if key.startswith("node:")][:SEED_COUNT]
    try:
        return [UUID(key) for key in keys]
    except ValueError:
        return []


def _article_path(path: str, node_type: str) -> str:
    return path.rsplit(".", maxsplit=1)[0] if node_type in PART_TYPES else path
