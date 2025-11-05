from __future__ import annotations

# Compatibility shim: delegate city selection flow to marketing module
from marketing.city_selection import (
    send_city_selection,
    send_city_selection_page2,
    handle_city_selection,
)

__all__ = [
    "send_city_selection",
    "send_city_selection_page2",
    "handle_city_selection",
]


