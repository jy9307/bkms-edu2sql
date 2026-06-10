import json
from pathlib import Path


def load_json(path: str | Path) -> any:
    """Load JSON data from a file."""
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


class Retriever:
    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.schema = load_json(self.data_dir / "schema_dictionary.json")
        self.rules = load_json(self.data_dir / "clarification_rules.json")
        self.examples = load_json(self.data_dir / "query_examples.json")

    def retrieve_schema_context(self, question: str) -> dict:
        """Retrieve relevant tables and metrics from the schema dictionary."""
        # Simple implementation: return all tables and metrics for now
        # In a more advanced version, we would filter based on keywords
        return self.schema

    def retrieve_clarification_rules(self, question: str) -> list[dict]:
        """Retrieve relevant clarification rules based on keywords."""
        candidates = []
        for rule in self.rules:
            score = 0
            for keyword in rule.get("trigger_keywords", []):
                if keyword in question:
                    score += 10
            
            score += rule.get("priority", 0)

            if score > rule.get("priority", 0):
                candidates.append((score, rule))
        
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [rule for score, rule in candidates]

    def retrieve_query_examples(self, question: str, limit: int = 3) -> list[dict]:
        """Retrieve relevant few-shot examples based on tags and keywords."""
        scored = []
        important_tokens = ["퀴즈", "제출", "AI", "토론", "읽기", "점수", "접속", "학년", "반"]
        
        for example in self.examples:
            score = 0
            example_text = " ".join([
                example.get("original_question", ""),
                example.get("resolved_question", ""),
                " ".join(example.get("tags", [])),
            ])
            
            for tag in example.get("tags", []):
                if tag in question:
                    score += 5
            
            for token in important_tokens:
                if token in question and token in example_text:
                    score += 3
            
            if score > 0:
                scored.append((score, example))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [example for score, example in scored[:limit]]
