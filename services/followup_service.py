from __future__ import annotations

# Thin compatibility layer to keep imports stable:
# `from services.followup_service import ...` will forward to the
# actual implementation under `marketing.services.followup_service`.

from marketing.services.followup_service import (  # noqa: F401
    FOLLOW_UP_1_DELAY_MINUTES,
    FOLLOW_UP_2_DELAY_MINUTES,
    FOLLOW_UP_1_TEXT,
    FOLLOW_UP_2_TEXT,
    acquire_followup_lock,
    release_followup_lock,
    schedule_next_followup,
    mark_customer_replied,
    due_customers_for_followup,
    send_followup1_interactive,
    send_followup2,
)

__all__ = [
    "FOLLOW_UP_1_DELAY_MINUTES",
    "FOLLOW_UP_2_DELAY_MINUTES",
    "FOLLOW_UP_1_TEXT",
    "FOLLOW_UP_2_TEXT",
    "acquire_followup_lock",
    "release_followup_lock",
    "schedule_next_followup",
    "mark_customer_replied",
    "due_customers_for_followup",
    "send_followup1_interactive",
    "send_followup2",
]


