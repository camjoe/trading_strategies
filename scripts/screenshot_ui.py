#!/usr/bin/env python3
"""Dev utility: capture screenshots of the paper trading UI.

Requires the UI to already be running (launch_ui.py).

Usage examples
--------------
# Test Account tab (default)
python scripts/screenshot_ui.py

# Specific tab
python scripts/screenshot_ui.py --tab accounts
python scripts/screenshot_ui.py --tab backtesting
python scripts/screenshot_ui.py --tab compare
python scripts/screenshot_ui.py --tab trades
python scripts/screenshot_ui.py --tab admin

# Open an account detail on the Accounts tab
python scripts/screenshot_ui.py --tab accounts --account my_account

# Wait for the Performance Analysis to finish loading (test-account tab)
python scripts/screenshot_ui.py --tab test-account --wait-analysis

# Custom output path
python scripts/screenshot_ui.py --output local/screenshots/my_shot.png

# Custom URL (if frontend runs on a different port)
python scripts/screenshot_ui.py --url http://127.0.0.1:5174

Available tabs
--------------
  accounts, test-account, compare, trades, backtesting,
  alt-strategies, docs, admin
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from scripts.ui_config import FRONTEND_PORT, UI_HOST


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = f"http://{UI_HOST}:{FRONTEND_PORT}"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "local" / "screenshots"
DEFAULT_VIEWPORT = (1440, 900)
ANALYSIS_LOADING_TEXT = "Loading analysis"

# How long (ms) to wait for network/UI to settle after tab click
TAB_SETTLE_MS = 800
# How long (ms) to wait for analysis panel before giving up
ANALYSIS_TIMEOUT_MS = 20_000


def build_output_path(output: str | None, tab: str) -> Path:
    if output:
        return Path(output)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"{tab}_{stamp}.png"


def capture(
    tab: str,
    url: str,
    output: Path,
    account: str | None,
    wait_analysis: bool,
    width: int,
    height: int,
    full_page: bool,
    headed: bool,
) -> None:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": width, "height": height})

        print(f"→ Opening {url} ...")
        page.goto(url, wait_until="networkidle")

        # Click the target tab
        tab_btn = page.locator(f'[data-tab="{tab}"]')
        if not tab_btn.is_visible():
            print(f"✗  Tab '{tab}' not found. Available tabs:", file=sys.stderr)
            btns = page.locator(".tab-btn").all()
            for b in btns:
                print(f"   {b.get_attribute('data-tab')}", file=sys.stderr)
            browser.close()
            raise ValueError(f"Tab '{tab}' not found")

        print(f"→ Clicking tab: {tab}")
        tab_btn.click()
        page.wait_for_timeout(TAB_SETTLE_MS)

        # Optional: open a specific account detail (accounts tab)
        if account:
            print(f"→ Looking for account card: {account}")
            card = page.locator(f'[data-account="{account}"]').first
            try:
                card.wait_for(timeout=5_000)
                card.click()
                page.wait_for_timeout(TAB_SETTLE_MS)
            except PWTimeout:
                print(f"✗  Account card for '{account}' not found — taking screenshot of tab as-is.", file=sys.stderr)

        # Optional: wait for Performance Analysis to finish loading
        if wait_analysis:
            print("→ Waiting for Performance Analysis to load...")
            try:
                panel = page.locator("#analysisPanel")
                panel.wait_for(timeout=ANALYSIS_TIMEOUT_MS)
                # Poll until the panel no longer says "Loading analysis"
                page.wait_for_function(
                    f"""() => {{
                        const el = document.querySelector('#analysisPanel');
                        return el && !el.textContent.includes('{ANALYSIS_LOADING_TEXT}');
                    }}""",
                    timeout=ANALYSIS_TIMEOUT_MS,
                )
                print("   ✓ Analysis panel loaded.")
            except PWTimeout:
                print("   ⚠  Analysis panel timed out — taking screenshot as-is.", file=sys.stderr)

        # Let any remaining async renders settle
        page.wait_for_timeout(300)

        print(f"→ Capturing {'full page' if full_page else 'viewport'} screenshot → {output}")
        page.screenshot(path=str(output), full_page=full_page)
        browser.close()
        print(f"✓  Saved: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a screenshot of the paper trading UI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--tab",
        default="test-account",
        help="Tab to open (default: test-account). Options: accounts, test-account, "
             "compare, trades, backtesting, alt-strategies, docs, admin",
    )
    parser.add_argument(
        "--account",
        default=None,
        metavar="NAME",
        help="Account name to open detail for (only used with --tab accounts)",
    )
    parser.add_argument(
        "--wait-analysis",
        action="store_true",
        help="Wait for the Performance Analysis panel to finish loading before screenshotting",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=f"Output file path (default: local/screenshots/<tab>_<timestamp>.png)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Base URL of the frontend (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_VIEWPORT[0],
        help=f"Viewport width (default: {DEFAULT_VIEWPORT[0]})",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_VIEWPORT[1],
        help=f"Viewport height (default: {DEFAULT_VIEWPORT[1]})",
    )
    parser.add_argument(
        "--no-full-page",
        dest="full_page",
        action="store_false",
        help="Capture only the visible viewport instead of the full page",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run with a visible browser window (useful for debugging)",
    )
    args = parser.parse_args()

    output = build_output_path(args.output, args.tab)

    try:
        capture(
            tab=args.tab,
            url=args.url,
            output=output,
            account=args.account,
            wait_analysis=args.wait_analysis,
            width=args.width,
            height=args.height,
            full_page=args.full_page,
            headed=args.headed,
        )
    except Exception as exc:
        print(f"✗  Screenshot failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
