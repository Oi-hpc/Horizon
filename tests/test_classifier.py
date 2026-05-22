"""Unit tests for AI category extraction."""

from src.ai.classifier import ContentClassifier


def test_extract_categories_accepts_valid_items():
    classifier = ContentClassifier(ai_client=None)  # type: ignore[arg-type]

    result = classifier._extract_categories(
        {
            "items": [
                {"index": 1, "category": "semiconductors"},
                {"index": "2", "category": "finance"},
                {"index": 3, "category": "real_estate"},
                {"index": 4, "category": "not-a-category"},
            ]
        }
    )

    assert result == {0: "semiconductors", 1: "finance", 2: "real_estate"}


def test_extract_categories_accepts_mapping_shape():
    classifier = ContentClassifier(ai_client=None)  # type: ignore[arg-type]

    result = classifier._extract_categories(
        {"items": {"1": "policy", "2": "shenzhen"}}
    )

    assert result == {0: "policy", 1: "shenzhen"}
