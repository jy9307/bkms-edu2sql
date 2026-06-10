import os
from typing import Any

from dotenv import load_dotenv


DEFAULT_ALLOWED_PREFIXES = ("select", "explain", "show", "with")

load_dotenv()


def get_db_config() -> dict[str, Any]:
    """Return PostgreSQL connection settings from environment variables."""
    config = {
        "host": os.getenv("DB_HOST") or "",
        "port": os.getenv("DB_PORT") or "5432",
        "dbname": os.getenv("DB_NAME") or "edu2sql",
        "user": os.getenv("DB_USER") or os.getenv("USER", ""),
        "password": os.getenv("DB_PASSWORD") or "",
    }

    return {key: value for key, value in config.items() if value}


def get_connection(readonly: bool = False):
    """Create a PostgreSQL connection."""
    import psycopg2

    dsn = os.getenv("DATABASE_URL")
    if dsn:
        print(f"Connecting using DATABASE_URL: {dsn[:20]}...")
        connection = psycopg2.connect(dsn)
    else:
        print("Connecting using individual parameters.")
        connection = psycopg2.connect(**get_db_config())

    if readonly:
        connection.set_session(readonly=True, autocommit=True)
    return connection


def run_read_only_sql(
    query: str,
    allowed_prefixes: tuple[str, ...] = DEFAULT_ALLOWED_PREFIXES,
    max_rows: int = 50,
) -> str:
    """Run a read-only SQL query and return a plain-text table result."""
    normalized = query.strip().lower()
    if not normalized.startswith(allowed_prefixes):
        allowed = ", ".join(prefix.upper() for prefix in allowed_prefixes)
        return f"ERROR: Only {allowed} statements are allowed."

    try:
        connection = get_connection(readonly=True)
        cursor = connection.cursor()
        cursor.execute(query)

        columns = [description[0] for description in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(max_rows) if columns else []

        cursor.close()
        connection.close()

        if not columns:
            return "(no results)"

        lines = [" | ".join(columns), "-" * len(" | ".join(columns))]
        lines.extend(" | ".join(str(value) for value in row) for row in rows)

        if len(rows) == max_rows:
            lines.append(f"(showing max {max_rows} rows; actual result may contain more)")

        return "\n".join(lines)
    except Exception as error:
        return f"SQL ERROR: {error}"


def main() -> None:
    """Run a small database connection check."""
    print("DB config:", get_db_config())
    print()
    print(run_read_only_sql("SELECT current_database() AS database, current_user AS user;"))


if __name__ == "__main__":
    main()
