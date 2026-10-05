from vcmi_mapgen.vcmi.formats.json_value import loads_relaxed


def test_relaxed_json_keeps_strings_whole() -> None:
    text = '{"url": "http://x//y", // note\n "list": [1, 2, /* gap */], "tab": "a\tb",\n}'
    assert loads_relaxed(text) == {"url": "http://x//y", "list": [1, 2], "tab": "a\tb"}
