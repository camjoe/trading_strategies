# UI Screenshot Utility

`scripts/screenshot_ui.py` captures full-page screenshots of the paper trading
frontend using Playwright (headless Chromium).  It is used by developers and AI
assistants to verify UI state without a live browser session.

---

## Prerequisites

1. **The UI must be running** before you take a screenshot:
   ```sh
   # From repo root, with venv active
   python scripts/launch_ui.py
   ```
   Default addresses: frontend `http://127.0.0.1:5173`, backend `http://127.0.0.1:8000`.

2. **Dependencies** — Playwright and Chromium must be installed:
   ```sh
   pip install -r requirements-dev.txt      # installs playwright package
   python -m playwright install chromium    # downloads the browser binary
   ```
   Both are needed once per environment.  The `playwright` package is declared in
   `requirements-dev.txt`.

---

## Setup (first time on a new machine)

```sh
# 1. Create and activate the virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate           # macOS / Linux

# 2. Install all project dependencies
pip install -r requirements-dev.txt

# 3. Install the Playwright browser binary
python -m playwright install chromium
```

---

## Basic usage

All commands assume the venv is active and you are in the repo root.

```sh
# Test Account tab (default)
python scripts/screenshot_ui.py

# Any other tab
python scripts/screenshot_ui.py --tab accounts
python scripts/screenshot_ui.py --tab compare
python scripts/screenshot_ui.py --tab backtesting
python scripts/screenshot_ui.py --tab trades
python scripts/screenshot_ui.py --tab alt-strategies
python scripts/screenshot_ui.py --tab admin
python scripts/screenshot_ui.py --tab docs
```

Output is saved to `local/screenshots/<tab>_<timestamp>.png` (gitignored).

---

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--tab NAME` | `test-account` | Which tab to open. See available tabs below. |
| `--account NAME` | — | Click into a specific account detail (use with `--tab accounts`). |
| `--wait-analysis` | off | Wait for the Performance Analysis panel to finish loading before capturing. |
| `--output PATH` | auto | Custom output file path. |
| `--url URL` | `http://127.0.0.1:5173` | Frontend base URL (override if running on a different port). |
| `--width N` | `1440` | Viewport width in pixels. |
| `--height N` | `900` | Viewport height in pixels. |
| `--no-full-page` | off | Capture viewport only instead of the full scrollable page. |
| `--headed` | off | Show the browser window (useful for debugging interactions). |

### Available tab names

```
accounts        alt-strategies
test-account    docs
compare         admin
trades
backtesting
```

---

## Common recipes

```sh
# Test Account — wait for Performance Analysis before capturing
python scripts/screenshot_ui.py --tab test-account --wait-analysis

# Open a specific account detail
python scripts/screenshot_ui.py --tab accounts --account my_account_bt

# Debug: see exactly what the browser is doing
python scripts/screenshot_ui.py --tab test-account --headed --wait-analysis

# Save to a specific path
python scripts/screenshot_ui.py --output local/screenshots/before_fix.png

# Narrow viewport to test responsive layout
python scripts/screenshot_ui.py --width 768 --height 1024
```

---

## For AI assistants (Copilot / bots)

To visually verify a UI change, run the script from within the session:

```python
# Example: capture the test account page and inspect the screenshot
import subprocess, sys
result = subprocess.run(
    [sys.executable, "scripts/screenshot_ui.py",
     "--tab", "test-account", "--wait-analysis"],
    capture_output=True, text=True
)
print(result.stdout)
# Screenshot path is on the last "✓  Saved:" line
```

The screenshot is saved to `local/screenshots/` and can be read back as an
image to verify layout, section spacing, or panel content.

**Important:** the UI must already be running before invoking the script.  If
`launch_ui.py` is not active, the script will fail with a connection error.
