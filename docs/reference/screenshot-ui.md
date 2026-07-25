# UI Screenshot Utility

Type: notes
Status: Active
Created: 2026-04-06
Last Reviewed: 2026-07-13
Purpose: Instructions for using scripts/screenshot_ui.py to capture full-page UI screenshots with Playwright.
Related: [UI Map](../maps/ui-map.md), [Scripts Map](../maps/scripts-map.md)

`scripts/screenshot_ui.py` captures full-page screenshots of the paper trading
frontend using Playwright (headless Chromium).  It is used by developers and AI
assistants to verify UI state without a live browser session.

---

## Prerequisites

1. **The UI must be running** before you take a screenshot:
   ```sh
    # From repo root, with venv active
    python -m scripts.launch_ui
    ```
   Default addresses come from `scripts/ui_config.py`: frontend `http://127.0.0.1:5173`,
   backend `http://127.0.0.1:8000`.

2. **Dependencies** — Playwright and Chromium must be installed:
   ```sh
   pip install -r requirements-dev.txt      # installs playwright package
   python -m playwright install chromium    # downloads the browser binary
   ```
   Both are needed once per environment.  The `playwright` package is declared in
   `requirements-dev.txt`.

## Basic usage

All commands assume the venv is active and you are in the repo root.

```sh
# Accounts tab (default)
python -m scripts.screenshot_ui

# Any other tab
python -m scripts.screenshot_ui --tab accounts
python -m scripts.screenshot_ui --tab compare
python -m scripts.screenshot_ui --tab portfolio
python -m scripts.screenshot_ui --tab backtesting
python -m scripts.screenshot_ui --tab strategy-lab
python -m scripts.screenshot_ui --tab autonomy-monitor
python -m scripts.screenshot_ui --tab alt-strategies
python -m scripts.screenshot_ui --tab admin
python -m scripts.screenshot_ui --tab docs
```

Output is saved to `local/screenshots/<tab>_<timestamp>.png` (gitignored).

---

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--tab NAME` | `accounts` | Which tab to open. See available tabs below. |
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
compare         admin
portfolio       docs
autonomy-monitor
backtesting
strategy-lab
```

Tab names match the `data-tab` attributes in
`apps/paper_trading_web/frontend/src/views/nav.html` (note the UI labels differ:
`compare` is shown as "Overview", `alt-strategies` as "Sentiment").

---

## Common recipes

```sh
# Accounts — wait for Performance Analysis before capturing
python -m scripts.screenshot_ui --tab accounts --wait-analysis

# Open a specific account detail
python -m scripts.screenshot_ui --tab accounts --account my_account_bt

# Debug: see exactly what the browser is doing
python -m scripts.screenshot_ui --tab accounts --headed --wait-analysis

# Save to a specific path
python -m scripts.screenshot_ui --output local/screenshots/before_fix.png

# Narrow viewport to test responsive layout
python -m scripts.screenshot_ui --width 768 --height 1024
```

---

## Verification workflow

For visual UI verification, capture the relevant tab and inspect the generated
image under `local/screenshots/`.

**Important:** the UI must already be running before invoking the script.  If
`launch_ui.py` is not active, the script will fail with a connection error.
