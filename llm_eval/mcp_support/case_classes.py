"""Capability-class classification for MCP tools.

Instead of enumerating a case per tool (which scales badly as servers grow),
tools are grouped into ~8 capability classes and only a few trait-varied
representatives per class are exercised. Tools with risky traits — pagination,
nested schemas, domain vocabulary, or destructive semantics — are never
collapsed into a representative; they always get their own case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Domain vocabulary is checked FIRST and wins over a generic read/write match,
# because these tools carry semantics a generic case would not exercise.
RE_DOMAIN = re.compile(
    r"(voice|audience|persona|personali[sz]e|experience|segment|campaign|journey)",
    re.IGNORECASE,
)
RE_READ_LIST = re.compile(r"^(get_all|list|find|search|fetch|count|read)_", re.IGNORECASE)
RE_READ_SINGLE = re.compile(r"(^get_a_|^get_an_|_single|^get_.*_by_)", re.IGNORECASE)
RE_READ_GENERIC = re.compile(r"^(get|read|fetch)_", re.IGNORECASE)
RE_CREATE = re.compile(r"^(create|add|insert)_", re.IGNORECASE)
RE_MUTATE = re.compile(r"^(update|set|patch|move|duplicate|import|migrate|bulk|rename)_", re.IGNORECASE)
RE_PUBLISH = re.compile(r"^(un)?publish", re.IGNORECASE)
RE_DESTRUCTIVE = re.compile(r"^(delete|remove|purge|drop)_", re.IGNORECASE)
RE_PAGINATION = re.compile(r"^(get_all|list)_", re.IGNORECASE)

CLASSES = (
    "readList",
    "readSingle",
    "writeCreate",
    "writeMutate",
    "writePublish",
    "destructive",
    "domainSpecial",
    "other",
)


def classify_tool_name(name: str) -> str:
    """Bucket a tool name into one of the capability classes."""
    name = name or ""
    if RE_DOMAIN.search(name):
        return "domainSpecial"
    if RE_DESTRUCTIVE.match(name):
        return "destructive"
    if RE_PUBLISH.match(name):
        return "writePublish"
    if RE_CREATE.match(name):
        return "writeCreate"
    if RE_MUTATE.match(name):
        return "writeMutate"
    if RE_READ_SINGLE.search(name):
        return "readSingle"
    if RE_READ_LIST.match(name):
        return "readList"
    if RE_READ_GENERIC.match(name):
        return "readSingle"
    return "other"


def has_nested_schema(input_schema: Optional[dict[str, Any]]) -> bool:
    """True if any top-level property is an object or array (nested shape)."""
    if not isinstance(input_schema, dict):
        return False
    props = input_schema.get("properties")
    if not isinstance(props, dict):
        return False
    for spec in props.values():
        if isinstance(spec, dict) and spec.get("type") in {"object", "array"}:
            return True
    return False


@dataclass
class ToolSpec:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


def is_split_trigger(tool: ToolSpec) -> bool:
    """A tool that must never be collapsed into a class representative."""
    if RE_PAGINATION.match(tool.name):
        return True
    if has_nested_schema(tool.input_schema):
        return True
    if RE_DOMAIN.search(tool.name):
        return True
    if RE_DESTRUCTIVE.match(tool.name):
        return True
    return False


def classify_tools(tools: list[ToolSpec]) -> dict[str, list[ToolSpec]]:
    """Group tools by capability class, preserving input order within a class."""
    buckets: dict[str, list[ToolSpec]] = {cls: [] for cls in CLASSES}
    for tool in tools:
        buckets[classify_tool_name(tool.name)].append(tool)
    return buckets


def select_representatives(members: list[ToolSpec], depth: int = 2) -> list[ToolSpec]:
    """Choose which tools in a class get their own case.

    Every split-trigger is always included; remaining slots up to ``depth`` are
    filled with non-trigger members. Tools that aren't selected are meant to be
    exercised shallowly (behavioral-only) elsewhere.
    """
    forced = [t for t in members if is_split_trigger(t)]
    rest = [t for t in members if not is_split_trigger(t)]
    selected = list(forced)
    for tool in rest:
        if len(selected) >= depth:
            break
        selected.append(tool)
    # Preserve original ordering.
    order = {id(t): i for i, t in enumerate(members)}
    selected.sort(key=lambda t: order.get(id(t), 0))
    return selected
