"""Lightweight, robust TOML reader and writer with zero extra dependencies."""
from __future__ import annotations

import re
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        raise ImportError("tomllib is required (built-in in Python 3.11+)")


def load_toml(content: str) -> dict[str, Any]:
    """Parse a TOML string into a dictionary."""
    return tomllib.loads(content)


def _format_value(val: Any) -> str:
    """Format a scalar or array value for TOML."""
    if isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, str):
        # Escape string
        escaped = (
            val.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    elif isinstance(val, (list, tuple)):
        items = [_format_value(item) for item in val]
        return f"[{', '.join(items)}]"
    else:
        escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


def _format_key(key: str) -> str:
    """Format a table key, quoting if necessary."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dump_toml(data: dict[str, Any]) -> str:
    """Serialize a dictionary into TOML format."""
    lines: list[str] = []

    # 1. Output top-level non-table keys first
    top_keys = [k for k, v in data.items() if not isinstance(v, dict)]
    for k in top_keys:
        lines.append(f"{_format_key(k)} = {_format_value(data[k])}")

    if top_keys:
        lines.append("")

    # 2. Output tables recursively
    def write_table(table_dict: dict[str, Any], path: list[str]) -> None:
        # Separate scalar values and nested tables
        scalars = [(k, v) for k, v in table_dict.items() if not isinstance(v, dict)]
        subtables = [(k, v) for k, v in table_dict.items() if isinstance(v, dict)]

        if path:
            header = ".".join(_format_key(p) for p in path)
            lines.append(f"[{header}]")

        for k, v in scalars:
            lines.append(f"{_format_key(k)} = {_format_value(v)}")

        if scalars and subtables:
            lines.append("")

        for sub_k, sub_dict in subtables:
            if lines and lines[-1] != "":
                lines.append("")
            write_table(sub_dict, path + [sub_k])

    top_tables = [(k, v) for k, v in data.items() if isinstance(v, dict)]
    for k, v in top_tables:
        if lines and lines[-1] != "":
            lines.append("")
        write_table(v, [k])

    return "\n".join(lines).strip() + "\n"
