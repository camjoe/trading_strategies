"""Shared UI host and port constants for launch_ui.py, launch_demo.py, and screenshot_ui.py."""

from __future__ import annotations

UI_HOST = "127.0.0.1"
BACKEND_PORT = "8000"
FRONTEND_PORT = "5173"

# Distinct ports for the offline demo so it can run alongside a live launch_ui
# session without a port conflict.
DEMO_BACKEND_PORT = "8001"
DEMO_FRONTEND_PORT = "5174"

# The sandbox gets its own pair again, so a test bed and the demo can be up at
# the same time without either standing in for the other.
SANDBOX_BACKEND_PORT = "8002"
SANDBOX_FRONTEND_PORT = "5175"
