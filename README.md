# Edu2SQL

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- OpenAI API key or Anthropic API key

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
cd Edu2SQL
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
ANTHROPIC_API_KEY=
DB_HOST=
DB_PORT=5432
DB_NAME=edu2sql
DB_USER=
DB_PASSWORD=
```

On macOS/Homebrew PostgreSQL, the default database user is usually your macOS username.
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

## Repository Structure

```text
.
+-- config/
|   +-- default.yaml
+-- src/
|   +-- edu2sql/
|       +-- __init__.py
|       +-- config.py
|       +-- db.py
+-- tests/
|   +-- test_config.py
+-- .env.example
+-- .gitignore
+-- environment.yml
+-- pyproject.toml
+-- README.md
```

## Notes

- Commit shared defaults in `config/default.yaml`.
- Put personal local settings in `config/local.yaml`.
- Put secrets in `.env`.
- Do not commit `.env` or `config/local.yaml`.