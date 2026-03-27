# utils.py (timezone-safe, no ZoneInfo required)
from datetime import datetime, timedelta, timezone

ROOMS_PER_PAGE = 12
ALERTS_PER_PAGE = 2

MMWAVE_STALE_SECS = 120
CAMERA_STALE_SECS = 120

SG_OFFSET = timedelta(hours=8)

def utcnow_naive() -> datetime:
    """UTC now, tz-naive (Mongo-friendly)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def dt_to_sg_str(dt) -> str:
    """Format UTC-naive datetime as Singapore time string (UTC+8)."""
    if not dt:
        return "-"
    if isinstance(dt, str):
        # Try to detect if string is already in SG time (naive check: if it matches the current SG time offset)
        try:
            s2 = dt.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(s2)
            # If the string is timezone-aware and already +08:00, just format as is
            if parsed.tzinfo is not None and parsed.tzinfo.utcoffset(parsed) == SG_OFFSET:
                return parsed.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
            # If the string is naive, assume it's already SG if hour > 7 (loose check)
            if parsed.tzinfo is None and parsed.hour > 7:
                return parsed.strftime("%Y-%m-%d %H:%M:%S")
            # Otherwise, treat as UTC and convert
            return (parsed + SG_OFFSET).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return dt
    # If dt is timezone-aware and already in +08:00, use as is
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) == SG_OFFSET:
        return dt.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    # If dt is naive and hour > 7, assume already SG
    if hasattr(dt, 'hour') and dt.tzinfo is None and dt.hour > 7:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    # Otherwise, treat as UTC and convert to SG
    return (dt + SG_OFFSET).strftime("%Y-%m-%d %H:%M:%S")

def dt_to_sg_hhmm(dt) -> str:
    if not dt:
        return "-"
    if isinstance(dt, str):
        try:
            s2 = dt.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(s2)
            if parsed.tzinfo is not None and parsed.tzinfo.utcoffset(parsed) == SG_OFFSET:
                return parsed.replace(tzinfo=None).strftime("%H:%M")
            if parsed.tzinfo is None and parsed.hour > 7:
                return parsed.strftime("%H:%M")
            return (parsed + SG_OFFSET).strftime("%H:%M")
        except Exception:
            return dt
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) == SG_OFFSET:
        return dt.replace(tzinfo=None).strftime("%H:%M")
    if hasattr(dt, 'hour') and dt.tzinfo is None and dt.hour > 7:
        return dt.strftime("%H:%M")
    return (dt + SG_OFFSET).strftime("%H:%M")

def now_str_sg() -> str:
    return dt_to_sg_str(utcnow_naive())

def get_occupancy_label(headcount: int, capacity: int) -> str:
    if headcount <= 0:
        return "Vacant"
    if headcount < capacity:
        return "Occupied"
    if headcount == capacity:
        return "Full"
    return "Overcapacity"

def is_sensor_occupied(headcount: int, mmwave_presence: int) -> bool:
    return bool(mmwave_presence == 1 or headcount > 0)

def paginate_items(items, page: int, per_page: int):
    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_items = items[start_idx:end_idx]

    start_item = 0 if total_items == 0 else start_idx + 1
    end_item = 0 if total_items == 0 else min(end_idx, total_items)

    return {
        "items": paged_items,
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "start_item": start_item,
        "end_item": end_item,
    }