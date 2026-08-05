"""Size-bounded safe YAML loading for future launcher metadata resolvers."""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from typing import Any as _Any

from py_modules.yaml import YAMLError as _YAMLError
from py_modules.yaml import parse as _pyyaml_parse
from py_modules.yaml import safe_load as _pyyaml_safe_load
from py_modules.yaml.events import AliasEvent as _AliasEvent
from py_modules.yaml.events import CollectionEndEvent as _CollectionEndEvent
from py_modules.yaml.events import CollectionStartEvent as _CollectionStartEvent
from py_modules.yaml.events import NodeEvent as _NodeEvent
from py_modules.yaml.loader import SafeLoader as _SafeLoader


__all__ = ("safe_load",)

_MAXIMUM_INPUT_BYTES = 1_048_576
_MAXIMUM_NESTING_DEPTH = 32
_MAXIMUM_NODES = 10_000


class _YamlStructureError(ValueError):
    """Raised when YAML exceeds the metadata-only structure policy."""


def _validate_structure(value: bytes) -> None:
    """Reject YAML structures that are unsuitable for small launcher metadata."""
    depth = 0
    node_count = 0
    try:
        for event in _pyyaml_parse(value, Loader=_SafeLoader):
            if isinstance(event, _AliasEvent):
                raise _YamlStructureError("YAML aliases are not permitted")
            if isinstance(event, _NodeEvent):
                node_count += 1
                if node_count > _MAXIMUM_NODES:
                    raise _YamlStructureError(
                        "YAML input exceeds the maximum node count"
                    )
            if isinstance(event, _CollectionStartEvent):
                depth += 1
                if depth > _MAXIMUM_NESTING_DEPTH:
                    raise _YamlStructureError(
                        "YAML input exceeds the maximum nesting depth"
                    )
            elif isinstance(event, _CollectionEndEvent):
                depth -= 1
    except (_YAMLError, RecursionError) as error:
        raise _YamlStructureError("YAML input has an invalid structure") from error


def safe_load(value: str | bytes, *, require_mapping: bool = False) -> _Any:
    """Parse bounded, acyclic YAML with PyYAML's pure-Python safe loader.

    Metadata resolvers that require a mapping should pass ``require_mapping=True``
    so list, scalar, and empty YAML roots fail closed. Malformed, unsafe, deeply
    nested, oversized, or aliased input always raises ``ValueError``.
    """
    if isinstance(value, str):
        encoded_value = value.encode("utf-8")
    elif isinstance(value, bytes):
        encoded_value = value
    else:
        raise TypeError("YAML input must be text or bytes")
    if len(encoded_value) > _MAXIMUM_INPUT_BYTES:
        raise ValueError("YAML input exceeds the maximum allowed size")

    try:
        _validate_structure(encoded_value)
        parsed = _pyyaml_safe_load(encoded_value)
    except (_YAMLError, RecursionError, _YamlStructureError) as error:
        raise ValueError(
            "YAML input is malformed, unsafe, or exceeds metadata limits"
        ) from error
    if require_mapping and not isinstance(parsed, _Mapping):
        raise ValueError("YAML metadata root must be a mapping")
    return parsed
