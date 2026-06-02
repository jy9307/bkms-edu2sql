from edu2sql.config import load_config


def test_load_default_config():
    config = load_config()

    assert config["app"]["name"] == "Edu2SQL"
    assert config["database"]["driver"] == "postgresql"
    assert config["pipeline"]["enable_clarification"] is True
