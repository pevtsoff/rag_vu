from dataclasses import dataclass


@dataclass(frozen=True)
class VersioningThresholds:
    """Similarity cut-offs; ``semantic`` values are cosine similarity mapped to 0..1."""

    semantic: float = 0.96
    duplicate_semantic: float = 0.995
    lexical_min: float = 0.5
    duplicate_lexical: float = 0.99

    @property
    def max_cosine_distance(self) -> float:
        """pgvector cosine distance (0..2) that corresponds to ``semantic``."""
        return 2.0 * (1.0 - self.semantic)
