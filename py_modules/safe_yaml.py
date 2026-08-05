"""Size-bounded safe YAML loading for future launcher metadata resolvers."""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from typing import Any as _Any

from py_modules.yaml import YAMLError as _YAMLError
from py_modules.yaml import safe_load as _pyyaml_safe_load


__all__ = ("safe_load",)

_MAXIMUM_INPUT_BYTES = 1_048_576


def safe_load(value: str | bytes, *, require_mapping: bool = False) -> _Any:
    """Parse bounded YAML with PyYAML's safe loader.

    Metadata resolvers that require a mapping should pass ``require_mapping=True``
    so list, scalar, and empty YAML roots fail closed.
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
        parsed = _pyyaml_safe_load(encoded_value)
    except _YAMLError as error:
        raise ValueError("YAML input is malformed or uses an unsafe tag") from error
    if require_mapping and not isinstance(parsed, _Mapping):
        raise ValueError("YAML metadata root must be a mapping")
    return parsed
