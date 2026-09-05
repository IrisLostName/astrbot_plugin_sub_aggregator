from subagg.sources.ordering import sort_sources


def test_lower_priority_number_is_processed_first_stably():
    sources = [
        {"name": "normal-first", "priority": 100},
        {"name": "highest", "priority": 1},
        {"name": "normal-second", "priority": 100},
    ]

    assert [source["name"] for source in sort_sources(sources)] == ["highest", "normal-first", "normal-second"]
