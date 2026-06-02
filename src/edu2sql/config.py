from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config/default.yaml") -> dict[str, Any]:
    """Load a YAML config file."""
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}
