import re
from typing import Any

FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", 
    "CREATE", "GRANT", "REVOKE", "COPY", "CALL", "EXECUTE"
]

ALLOWED_TABLES = [
    "users", "sessions", "activities", "activity_runs", 
    "submissions", "activity_logs", "access_logs", 
    "quiz_answers", "discussion_posts", "writing_submissions"
]


class SQLValidator:
    def __init__(self, allowed_tables: list[str] = ALLOWED_TABLES):
        self.allowed_tables = allowed_tables

    def validate(self, sql: str) -> dict[str, Any]:
        """Validate a SQL query for safety and correctness."""
        sql_upper = sql.upper().strip()

        # 1. Must start with SELECT or WITH
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            return {
                "valid": False,
                "errors": ["SQL must start with SELECT or WITH."]
            }

        # 2. Check for forbidden keywords
        for keyword in FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", sql_upper):
                return {
                    "valid": False,
                    "errors": [f"Forbidden keyword found: {keyword}"]
                }

        # 3. Check for multiple statements
        if ";" in sql.rstrip(";") :
            return {
                "valid": False,
                "errors": ["Multiple SQL statements are not allowed."]
            }

        # 4. (Optional) Check for allowed tables
        # This is a bit complex with regex, but we can do a simple check
        # For MVP, we might skip strict table validation or do a basic keyword check
        
        return {
            "valid": True,
            "sql": self.ensure_limit(sql),
            "errors": []
        }

    def ensure_limit(self, sql: str, default_limit: int = 50) -> str:
        """Ensure the query has a LIMIT clause."""
        if "LIMIT" not in sql.upper():
            return sql.rstrip().rstrip(";") + f" LIMIT {default_limit};"
        return sql
