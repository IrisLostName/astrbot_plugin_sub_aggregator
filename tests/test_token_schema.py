import json
from pathlib import Path


def test_access_token_is_declared_in_schema():
    schema = json.loads((Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))
    assert "access_token" in schema
    assert schema["access_token"]["type"] == "string"
