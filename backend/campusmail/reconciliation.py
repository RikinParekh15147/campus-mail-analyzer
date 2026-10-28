"""Keep manually corrected entity dates and their optional times aligned."""

from datetime import date, datetime, timedelta


def align_date_times(item, field, target):
    """Move existing time instants by the same calendar-day delta as a date edit."""
    if field not in ("date", "due_date"):
        return item
    previous = item.get(field)
    if not previous or previous == target:
        return {**item, field: target}
    delta = date.fromisoformat(target) - date.fromisoformat(previous)
    result = {**item, field: target}
    time_fields = ("due_at",) if field == "due_date" else ("start", "end")
    for name in time_fields:
        stamp = item.get(name)
        if stamp:
            result[name] = (datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                            + timedelta(days=delta.days)).isoformat()
    return result
