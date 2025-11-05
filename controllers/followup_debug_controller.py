from __future__ import annotations

# Compatibility shim:
# keep import path stable: controllers.followup_debug_controller
# real implementation lives under marketing.controllers.followup_debug_controller

from marketing.controllers.followup_debug_controller import router  # noqa: F401

__all__ = ["router"]


