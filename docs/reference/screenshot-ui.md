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

## Usage

Flags, defaults, and worked examples live in the script itself:

```sh
python -m scripts.screenshot_ui --help
```

Output is saved to `local/screenshots/<tab>_<timestamp>.png` (gitignored).

## Tab names

`--tab` takes no `choices`, so `--help` will not list these. They match the `data-tab` attributes in
`apps/paper_trading_web/frontend/src/views/nav.html`:

```
accounts        backtesting       alt-strategies
compare         strategy-lab      admin
portfolio       autonomy-monitor  docs
```

Two UI labels differ from their tab name: `compare` is shown as **Overview**, `alt-strategies` as
**Sentiment**.

## Troubleshooting

The UI must already be running. If `launch_ui.py` is not active the script fails with a connection
error — that is the usual cause, not a Playwright problem.
