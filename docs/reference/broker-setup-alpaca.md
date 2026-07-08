# Alpaca Setup

Type: notes
Status: Draft
Created: 2026-06-24
Last Reviewed: 2026-06-24
Purpose: Operator setup and connection checklist for Alpaca broker integration (adapter not yet implemented).
Related: [Broker Integration Reference](broker-integration.md), [IBKR Setup](broker-setup-ibkr.md)

## Purpose

Setup and connection guide for the Alpaca broker path. Alpaca uses a cloud-based REST API — no local gateway process is required, unlike IBKR.

**Status:** The Alpaca adapter is not yet implemented in this codebase. This document captures the expected setup flow for when the integration is built. See [Extending Broker Support](broker-integration.md#extending-broker-support) in `broker-integration.md` for the implementation checklist.

## Overview

Alpaca exposes a REST API directly. Authentication uses an API Key and Secret obtained from the Alpaca dashboard. No local proxy or gateway is needed.

Two base URLs:

| Environment | Base URL |
|---|---|
| Paper | `https://paper-api.alpaca.markets` |
| Live | `https://api.alpaca.markets` |

Expected `broker_type` value: `alpaca` (not yet registered in `src/infrastructure/brokers/factory.py`).

## Setup Checklist

_To be completed when the Alpaca adapter is implemented._

- [ ] Create an Alpaca account at [alpaca.markets](https://alpaca.markets)
- [ ] Generate API Key + Secret from the Alpaca dashboard (API Keys section)
- [ ] Prepare a private config file or set environment variables with credentials
- [ ] Verify paper-trading connectivity with a smoke test
- [ ] Confirm `alpaca` is registered in `src/infrastructure/brokers/factory.py`

## Expected Connection Flow

1. **Obtain credentials** from the [Alpaca dashboard](https://app.alpaca.markets) → API Keys section.

2. **Configure the app** — expected environment variables (to be confirmed when the adapter is built):

```sh
export TRADING_ALPACA_API_KEY="your-api-key"
export TRADING_ALPACA_API_SECRET="your-api-secret"
export TRADING_ALPACA_BASE_URL="https://paper-api.alpaca.markets"
```

3. **Verify connectivity** with a smoke test once the Alpaca adapter and smoke-test entrypoint are implemented.

4. **Run the module or script** as needed.

## Private Config File

_Format TBD — expected to mirror the IBKR private config approach._

Example expected structure:

```json
{
  "api_key": "your-api-key",
  "api_secret": "your-api-secret",
  "base_url": "https://paper-api.alpaca.markets"
}
```

Never commit API keys or secrets to the repository.

## Related Docs

- [`broker-integration.md`](broker-integration.md) — broker architecture, adapter wiring, safety guards, implementation checklist
- [`broker-setup-ibkr.md`](broker-setup-ibkr.md) — IBKR setup (reference for parallel Alpaca setup)
