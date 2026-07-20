"""Tests for capability-class classification and representative selection."""
from llm_eval.mcp_support.case_classes import (
    ToolSpec,
    classify_tool_name,
    classify_tools,
    has_nested_schema,
    is_split_trigger,
    select_representatives,
)


def test_canonical_bucketing():
    assert classify_tool_name("list_documents") == "readList"
    assert classify_tool_name("get_all_entries") == "readList"
    assert classify_tool_name("get_a_single_entry") == "readSingle"
    assert classify_tool_name("create_entry") == "writeCreate"
    assert classify_tool_name("update_entry") == "writeMutate"
    assert classify_tool_name("publish_entry") == "writePublish"
    assert classify_tool_name("delete_entry") == "destructive"
    assert classify_tool_name("frobnicate") == "other"


def test_domain_special_wins_over_generic_read():
    # A domain verb outranks a generic read prefix.
    assert classify_tool_name("get_audience_segment") == "domainSpecial"
    assert classify_tool_name("list_personalize_experiences") == "domainSpecial"


def test_has_nested_schema():
    assert has_nested_schema({"properties": {"body": {"type": "object"}}})
    assert has_nested_schema({"properties": {"items": {"type": "array"}}})
    assert not has_nested_schema({"properties": {"id": {"type": "string"}}})
    assert not has_nested_schema(None)


def test_is_split_trigger():
    assert is_split_trigger(ToolSpec("get_all_entries"))
    assert is_split_trigger(ToolSpec("delete_thing"))
    assert is_split_trigger(ToolSpec("get_persona"))
    assert is_split_trigger(ToolSpec("get_x", input_schema={"properties": {"b": {"type": "object"}}}))
    assert not is_split_trigger(ToolSpec("get_x", input_schema={"properties": {"id": {"type": "string"}}}))


def test_select_representatives_caps_but_keeps_triggers():
    members = [
        ToolSpec("get_one"),
        ToolSpec("get_two"),
        ToolSpec("get_three"),
        ToolSpec("get_all_entries"),  # split trigger, beyond depth
    ]
    selected = select_representatives(members, depth=2)
    names = [t.name for t in selected]
    assert "get_all_entries" in names   # trigger always kept
    assert len(selected) <= 3           # 2 normal + forced trigger


def test_classify_tools_groups_by_class():
    tools = [ToolSpec("list_x"), ToolSpec("create_x"), ToolSpec("delete_x")]
    buckets = classify_tools(tools)
    assert [t.name for t in buckets["readList"]] == ["list_x"]
    assert [t.name for t in buckets["writeCreate"]] == ["create_x"]
    assert [t.name for t in buckets["destructive"]] == ["delete_x"]
