import json
import sqlite3


def dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_string_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def load_scope_map(value: object) -> dict[str, list[str]]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(key): [
            str(item)
            for item in items
            if str(item).strip()
        ]
        for key, items in parsed.items()
        if isinstance(items, list)
    }


def load_object_list(value: object) -> list[dict]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def load_json_object(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def row_value(
    row: sqlite3.Row,
    column: str,
    default: object = None,
) -> object:
    return row[column] if column in row.keys() else default


def row_str(
    row: sqlite3.Row,
    column: str,
    default: str = "",
) -> str:
    value = row_value(row, column, default)
    return str(value) if value is not None else default


def safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
