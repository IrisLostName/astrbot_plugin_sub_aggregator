import json
from pathlib import Path


def test_source_notify_changes_is_addable_and_defaults_on():
    schema = json.loads((Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))
    item = schema["subscription_sources"]["templates"]["source"]["items"]["notify_changes"]
    assert item["type"] == "bool"
    assert item["default"] is True
