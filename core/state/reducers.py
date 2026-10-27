"""
State Reducer Function

Annotated reducer for LangGraph StateGraph that handles state merging when concurrent node executions occur.

Reducer Rules:
- keep_non_empty: String/scalar fields, retain non-null values (new values first)
- merge_dict: Dictionary fields, intelligent merging (special processing of historical fields)
- keep_latest_list: List fields, always take the latest value
"""

from typing import Any


def keep_non_empty(left: Any, right: Any) -> Any:
    """Keep non-null values, use right (new value) first

    Used for string/scalar fields to avoid overwriting existing results when executing parallel nodes.
    """
    if right:
        return right
    return left if left else right


def merge_dict(left: dict, right: dict) -> dict:
    """Smart merge of two dictionaries to handle concurrent updates

    Special handling: for the history field of debate status (*_history) , 
    Prioritize non-null values ​​to avoid being overwritten by empty strings.
    """
    if left is None:
        return right
    if right is None:
        return left

    result = left.copy()

    # Historical fields that require special treatment
    history_fields = [
        'bull_history', 'bear_history', 'history',
        'risky_history', 'safe_history', 'neutral_history'
    ]

    for key, value in right.items():
        # For history fields, only update if the new value is non-null
        if key in history_fields:
            old_value = result.get(key, "")
            # If the new value is null but the old value is not null, keep the old value
            if not value and old_value:
                continue
            # If both are non-empty, keep the longer one (contains more content)
            if value and old_value and len(old_value) > len(value):
                continue
        result[key] = value

    return result


def keep_latest_list(left: Any, right: Any) -> Any:
    """List fields always take the latest value, allowing explicit clearing of message history with an empty list."""
    if right is None:
        return left
    return right
