from __future__ import annotations

# Compatibility shim to preserve import path controllers.auto_welcome_controller
# Actual implementation lives under marketing.controllers.auto_welcome_controller

from marketing.controllers.auto_welcome_controller import (  # noqa: F401
    router,
    _send_template,
)

__all__ = [
    "router",
    "_send_template",
]


