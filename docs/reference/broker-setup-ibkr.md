# IBKR Client Portal Gateway Setup

Type: notes
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-06-24
Purpose: Operator setup and connection checklist for Interactive Brokers via the Client Portal Gateway.
Related: [Broker Integration Reference](broker-integration.md), [Runtime Operations Runbook](../runbooks/runtime-operations.md)

## Purpose

Step-by-step guide for operators to install, start, and connect to the Interactive Brokers Client Portal Gateway — the local reverse-proxy that enables the IBKR Web API path (`interactive_brokers_web`).

For code-level architecture, adapter wiring, and safety guards see [`broker-integration.md`](broker-integration.md).

## Overview

The IBKR Web API path uses a locally-running Client Portal Gateway (`clientportal.gw`) that proxies requests to IBKR's servers. The gateway handles authentication and session management; the app connects to it over localhost.

The gateway is a standalone Java process distributed by Interactive Brokers. It does not require a TWS installation.

## Setup Checklist

Before running any broker-connected module, confirm:

- [ ] `clientportal.gw` is downloaded and available (e.g., `~/Downloads/clientportal.gw`)
- [ ] `bin/run.sh` is present and executable
- [ ] `root/conf.yaml` is present and configured
- [ ] IBKR Paper account credentials are available
- [ ] Private config JSON file is prepared (see [Private Config File](#private-config-file))

## Connection Flow

1. **Start the gateway:**

```sh
cd ~/Downloads/clientportal.gw
bin/run.sh root/conf.yaml
```

The gateway starts on `https://localhost:5000` by default.

2. **Authenticate:** Open `https://localhost:5000` in a browser and log in with your IBKR Paper account credentials.

3. **Configure the app:** Point to your private config file:

```sh
export TRADING_IBKR_WEB_API_CONFIG="$HOME/Desktop/brokers/config.json"
```

Or set individual environment variables — see [Broker Integration Reference — IBKR Web API Configuration](broker-integration.md#ibkr-web-api-configuration) for the full list.

4. **Verify connectivity** with the smoke test:

```sh
.venv\Scripts\python -m scripts.ibkr_web_api_smoke_test   # Windows
.venv/bin/python -m scripts.ibkr_web_api_smoke_test        # macOS/Linux
```

5. **Run the module or script** as needed.

## Private Config File

Keep credentials outside the repository. Store them in a private JSON file and reference it via `TRADING_IBKR_WEB_API_CONFIG`.

Example structure:

```json
{
  "account_id": "U1234567",
  "base_url": "https://localhost:5000/v1/api",
  "headers": {
    "Cookie": "api=replace-me-locally"
  },
  "verify_ssl": false,
  "timeout_seconds": 10,
  "keepalive_enabled": true,
  "keepalive_interval_seconds": 60
}
```

Never commit account IDs, session tokens, or cookies to the repository.

## Smoke Test

Read-only test — validates session, auth, account visibility, ledger, and positions:

```sh
.venv\Scripts\python -m scripts.ibkr_web_api_smoke_test
```

Optional paper-order lifecycle check (paper account only):

```sh
.venv\Scripts\python -m scripts.ibkr_web_api_smoke_test \
  --paper-order-check \
  --paper-order-symbol AAPL \
  --paper-order-limit-price 1.00
```

Use clearly non-marketable limit prices. Cancellation is best-effort — order states may remain pre-submission outside market hours.

## Related Docs

- [`broker-integration.md`](broker-integration.md) — broker architecture, adapter wiring, account fields, live-trading safety
- [`broker-setup-alpaca.md`](broker-setup-alpaca.md) — Alpaca setup (parallel broker path, not yet implemented)
- [`runbooks/runtime-operations.md`](../runbooks/runtime-operations.md) — runtime operator workflow
