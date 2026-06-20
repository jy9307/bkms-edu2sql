# Edu2SQL

Edu2SQL is a skeleton NL2SQL project for education-domain questions. It takes a teacher-style natural language question, retrieves schema and example context, generates read-only PostgreSQL, validates it, and returns an answer.

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- OpenAI API key

If PostgreSQL is not installed, install it first.

```bash
brew install postgresql@16
brew services start postgresql@16
```

Check installation:

```bash
psql --version
createdb --version
```

### 1. Clone repository

```bash
git clone <repository-url>
cd bkms-edu2sql
```

### 2. Create environment

Use either `venv` or `conda`.

#### venv

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

#### conda

```bash
conda env create -f environment.yml
conda activate edu2sql
```

### 3. Create local environment file

```bash
cp .env.example .env
```

Fill in local secrets and database settings in `.env`.

```bash
OPENAI_API_KEY=
DATABASE_URL=postgresql:///edu2sql
DB_HOST=
DB_PORT=5432
DB_NAME=edu2sql
DB_USER=
DB_PASSWORD=
```

`DATABASE_URL` takes priority if it is set.
If `DATABASE_URL` is empty, the app falls back to `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
If `DB_USER` is empty, the app uses the current OS user.

### 4. Prepare PostgreSQL database

```bash
createdb edu2sql
```

If the database already exists, skip this step.

If you use a custom PostgreSQL user, specify it explicitly.

```bash
createdb -U <username> edu2sql
```

### 5. Check setup

```bash
python -m pytest
```

Check database connection:

```bash
python -m edu2sql.db
```

If you installed the package with `pip install -e ".[dev]"`, you can also run:

```bash
edu2sql-db-check
```

### 6. Run the Streamlit app

```bash
streamlit run streamlit_app.py
```

The app shows:

- Example teacher questions
- Current DB connection status
- Retrieved context, SQL path, DB result, and agent state

## Repository Structure

```text
.
+-- config/
|   +-- default.yaml
+-- data/
+   +-- clarification_rules.json
+   +-- query_examples.json
+   +-- schema_dictionary.json
+-- docs/
+   +-- lms_database_schema_spec.md
+   +-- nl2sql_agent_flow_and_clarification.md
+   +-- nl2sql_agent_implementation_spec.md
+-- src/
|   +-- edu2sql/
|       +-- __init__.py
|       +-- agent.py
|       +-- agent_graph.py
|       +-- config.py
|       +-- db.py
|       +-- retriever.py
|       +-- sql_validator.py
+-- tests/
|   +-- test_agent_flow.py
|   +-- test_config.py
+-- .env.example
+-- environment.yml
+-- pyproject.toml
+-- streamlit_app.py
+-- test_agent_graph_chat.py
+-- test_agent_interactive.py
+-- test_agent_real_chat.py
+-- README.md
```

## Notes

- Commit shared defaults in `config/default.yaml`.
- Put secrets in `.env`.
- Do not commit `.env`.
- The package currently uses OpenAI for generation and PostgreSQL for execution.
