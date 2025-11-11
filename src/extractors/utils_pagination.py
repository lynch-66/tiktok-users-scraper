thonfrom typing import Any, Dict, Optional

def get_has_more_flag(payload: Dict[str, Any]) -> bool:
    """
    Infer whether more pages are available from a TikTok search payload.

    We look for several possible fields, falling back to False if none exist.
    """
    if not isinstance(payload, dict):
        return False

    # Common patterns: top-level hasMore or data.has_more
    has_more = payload.get("hasMore")
    if isinstance(has_more, bool):
        return has_more
    if isinstance(has_more, int):
        return has_more != 0

    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("has_more") or data.get("hasMore")
        if isinstance(nested, bool):
            return nested
        if isinstance(nested, int):
            return nested != 0

    return False

def get_next_cursor(payload: Dict[str, Any]) -> Optional[int]:
    """
    Extract the next cursor value from the payload.

    Different shapes are supported:
    - payload["cursor"]
    - payload["data"]["cursor"]
    """
    if not isinstance(payload, dict):
        return None

    cursor = payload.get("cursor")
    if isinstance(cursor, int):
        return cursor
    if isinstance(cursor, str) and cursor.isdigit():
        return int(cursor)

    data = payload.get("data")
    if isinstance(data, dict):
        nested_cursor = data.get("cursor")
        if isinstance(nested_cursor, int):
            return nested_cursor
        if isinstance(nested_cursor, str) and nested_cursor.isdigit():
            return int(nested_cursor)

    return None

def should_continue_pagination(
    collected_count: int,
    max_items: int,
    has_more_flag: bool,
) -> bool:
    """
    Decide whether another page of data should be requested.
    """
    if collected_count >= max_items:
        return False
    if not has_more_flag:
        return False
    return True