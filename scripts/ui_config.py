"""Shared UI host and port constants for launch_ui.py, launch_demo.py, and screenshot_ui.py."""

from __future__ import annotations

UI_HOST = "127.0.0.1"
BACKEND_PORT = "8000"
FRONTEND_PORT = "5173"

# Distinct ports for the offline demo so it can run alongside a live launch_ui
# session without a port conflict.
DEMO_BACKEND_PORT = "8001"
DEMO_FRONTEND_PORT = "5174"
