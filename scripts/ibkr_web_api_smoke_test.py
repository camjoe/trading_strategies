"""Manual smoke test for the IBKR Client Portal / Web API integration.

This script is intentionally operator-run only. It uses the existing
InteractiveBrokersWebClient with private configuration loaded from env vars or
an external config file referenced by TRADING_IBKR_WEB_API_CONFIG.

It performs a read-only smoke test:
- session/auth/account validation via client.connect()
- ledger fetch
- summary fetch
- positions fetch

No orders are placed.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from typing import TextIO

import httpx

from trading.brokers.ib_web_client import InteractiveBrokersWebClient, load_ib_web_api_settings
from trading.utils.coercion import coerce_float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only IBKR Web API smoke test against the local Client Portal Gateway.",
    )
    return parser.parse_args()


def _mask_account_id(account_id: str) -> str:
    value = account_id.strip()
    if not value:
        return "<missing>"
    if len(value) <= 4:
        return "*" * len(value)
    prefix = value[:2]
    suffix = value[-2:]
    return f"{prefix}{'*' * max(0, len(value) - len(prefix) - len(suffix))}{suffix}"


def _redact(text: str, account_id: str) -> str:
    return text.replace(account_id, _mask_account_id(account_id)) if account_id else text


def _extract_amount(payload: Mapping[str, object], key: str) -> str | None:
    raw = payload.get(key)
    if isinstance(raw, Mapping):
        raw = raw.get("amount")
    amount = coerce_float(raw)
    if amount is None:
        return None
    return f"{amount:,.2f}"


def _print_metric(out: TextIO, label: str, value: str | None) -> None:
    if value is not None:
        print(f"  {label}: {value}", file=out)


def run_smoke_test(
    client: InteractiveBrokersWebClient,
    *,
    account_id: str,
    out: TextIO,
) -> None:
    masked_account_id = _mask_account_id(account_id)
    client.connect()
    print(f"✓ Session validated for account {masked_account_id}", file=out)

    ledger = client.fetch_ledger()
    summary = client.fetch_summary()
    positions = client.fetch_positions()

    base_ledger = ledger.get("BASE")
    currency_bucket_count = sum(1 for value in ledger.values() if isinstance(value, Mapping))

    print(f"✓ Ledger loaded ({currency_bucket_count} currency bucket(s))", file=out)
    if isinstance(base_ledger, Mapping):
        _print_metric(out, "Cash balance (BASE)", _extract_amount(base_ledger, "cashbalance"))
        _print_metric(
            out,
            "Net liquidation (BASE)",
            _extract_amount(base_ledger, "netliquidationvalue"),
        )

    print("✓ Summary loaded", file=out)
    _print_metric(out, "Buying power", _extract_amount(summary, "buyingpower"))
    _print_metric(out, "Net liquidation", _extract_amount(summary, "netliquidation"))

    print(f"✓ Positions loaded ({len(positions)} row(s))", file=out)


def main() -> int:
    parse_args()
    settings = None
    client = None

    try:
        settings = load_ib_web_api_settings()
        client = InteractiveBrokersWebClient(settings)
        run_smoke_test(client, account_id=settings.account_id, out=sys.stdout)
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        message = str(exc)
        if settings is not None:
            message = _redact(message, settings.account_id)
        print(f"✗ IBKR Web API smoke test failed: {message}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
