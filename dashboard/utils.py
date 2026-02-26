from datetime import datetime, timedelta

# -----------------------------
# Config (pagination sizes)
# -----------------------------
ROOMS_PER_PAGE = 12   # set to 5 / 10 / 12 depending on what you want
ALERTS_PER_PAGE = 2   # set to 2 or 3 (UI preference)

# -----------------------------
# Mock room data (admin overview)
# DR-01 is your "live" prototype room
# Others are mock rows to demonstrate scalability
# -----------------------------
ROOMS = [
    {
        "room_id": "SIT-DR-01",
        "room_name": "SIT DR-01",
        "capacity": 6,
        "booking_status": "Booked",
        "headcount": 3,
        "mmwave_presence": 1,
        "data_source": "Live",
    },
    {
        "room_id": "SIT-DR-02",
        "room_name": "SIT DR-02",
        "capacity": 6,
        "booking_status": "Booked",
        "headcount": 0,
        "mmwave_presence": 0,
        "data_source": "Mock",
    },
    {
        "room_id": "SIT-DR-03",
        "room_name": "SIT DR-03",
        "capacity": 8,
        "booking_status": "Free",
        "headcount": 0,
        "mmwave_presence": 0,
        "data_source": "Mock",
    },
    {
        "room_id": "SIT-DR-04",
        "room_name": "SIT DR-04",
        "capacity": 6,
        "booking_status": "Booked",
        "headcount": 6,
        "mmwave_presence": 1,
        "data_source": "Mock",
    },
    {
        "room_id": "SIT-DR-05",
        "room_name": "SIT DR-05",
        "capacity": 10,
        "booking_status": "Booked",
        "headcount": 2,
        "mmwave_presence": 1,
        "data_source": "Mock",
    },
]

def now_str():
    """Return current timestamp as formatted string"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_occupancy_label(headcount: int, capacity: int) -> str:
    """Get occupancy status label based on headcount and capacity"""
    if headcount <= 0:
        return "Vacant"
    if headcount < capacity:
        return "Occupied"
    if headcount == capacity:
        return "Full"
    return "Overcapacity"

def is_sensor_occupied(headcount: int, mmwave_presence: int) -> bool:
    """Determine if sensors indicate occupancy"""
    return bool(mmwave_presence == 1 or headcount > 0)

def paginate_items(items, page: int, per_page: int):
    """Paginate a list of items"""
    total_items = len(items)
    total_pages = max(1, (total_items + per_page - 1) // per_page)

    # clamp page
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_items = items[start_idx:end_idx]

    if total_items == 0:
        start_item = 0
        end_item = 0
    else:
        start_item = start_idx + 1
        end_item = min(end_idx, total_items)

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
