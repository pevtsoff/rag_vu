import pytest

from app.domain.documents.breadcrumbs import join_breadcrumbs


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["Law", " Article 1 ", ""], "Law > Article 1"),
        ({"items": ["Law", "Article 2"]}, "Law > Article 2"),
        ({"a": "Law", "b": "Article 3"}, "Law > Article 3"),
        (" Law > Article 4 ", "Law > Article 4"),
        (None, ""),
    ],
)
def test_join_breadcrumbs_supports_stored_shapes(value: object, expected: str) -> None:
    assert join_breadcrumbs(value, " > ") == expected
