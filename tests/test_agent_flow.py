import pytest
from edu2sql.retriever import Retriever
from edu2sql.sql_validator import SQLValidator


def test_retriever_load():
    retriever = Retriever()
    assert retriever.schema is not None
    assert len(retriever.rules) > 0
    assert len(retriever.examples) > 0


def test_retrieve_clarification_rules():
    retriever = Retriever()
    rules = retriever.retrieve_clarification_rules("요즘 참여율 어때?")
    assert len(rules) > 0
    # Should find 'ambiguous_recent' or 'ambiguous_participation_rate'
    ids = [r["id"] for r in rules]
    assert "ambiguous_recent" in ids or "ambiguous_participation_rate" in ids


def test_retrieve_query_examples():
    retriever = Retriever()
    examples = retriever.retrieve_query_examples("3학년 2반 퀴즈")
    assert len(examples) > 0
    assert any("quiz" in (ex.get("tags", [])) for ex in examples)


def test_sql_validator_valid():
    validator = SQLValidator()
    result = validator.validate("SELECT * FROM users")
    assert result["valid"] is True
    assert "LIMIT 50" in result["sql"]


def test_sql_validator_invalid_command():
    validator = SQLValidator()
    result = validator.validate("DROP TABLE users")
    assert result["valid"] is False
    assert "SQL must start with SELECT or WITH" in result["errors"][0]


def test_sql_validator_forbidden_keyword():
    validator = SQLValidator()
    result = validator.validate("SELECT * FROM users; DELETE FROM users")
    assert result["valid"] is False
    assert "Multiple SQL statements are not allowed" in result["errors"][0]


def test_sql_validator_forbidden_keyword_inline():
    validator = SQLValidator()
    result = validator.validate("SELECT name FROM users WHERE id IN (DELETE FROM users)")
    assert result["valid"] is False
    assert "Forbidden keyword found: DELETE" in result["errors"][0]
