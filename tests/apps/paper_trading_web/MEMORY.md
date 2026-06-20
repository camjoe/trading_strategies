# UI Backend Test Debug Memory

This note records a historical regression-sweep investigation around backend
HTTP-style route testing.

## What Failed

During the broader regression sweep, the HTTP-style UI backend tests appeared to
hang instead of failing fast.

The passing neighbor file
`tests/apps/paper_trading_web/backend/test_contract_mapping.py` was useful as a
contrast: it does not start the FastAPI app and only tests pure
request-to-command mapping helpers.

## What Was Checked

The debugging sequence was:

1. confirm the hang happens when the `api_client` fixture constructs the backend app
2. verify whether the issue is app-specific or `TestClient`-specific
3. verify whether an alternate transport path works
4. decide whether the next fix belongs in the fixture or in the test design

The key checks were:

- `TestClient(app)` hangs even for a minimal trivial `FastAPI()` app in this environment
- `httpx.AsyncClient(..., transport=httpx.ASGITransport(app=...))` works for a
  minimal async FastAPI app
- the real `paper_trading_ui.backend.main.app` still hangs even for a simple
  `/health` request when driven through the alternate transport path

## What We Learned

The hang is not just one broken route test.

The evidence points to a framework/runtime issue in this environment around the
sync FastAPI route-dispatch path used by the backend app:

- the failure is broader than one test file
- the failure is broader than Starlette `TestClient` alone
- the minimal async app path succeeds, but the real sync-route app path still stalls

That means a global fixture rewrite is risky, because many UI backend tests rely on
the same `api_client` pattern and a fixture-level workaround could spread a bad
assumption through the whole `tests/apps/paper_trading_web/` area.

## Important Current State

The historical fixture experiments described above are no longer the active
testing strategy.

## Recommended Next Step

Prefer API-route tests under `tests/apps/paper_trading_web/backend/routes/` as the
primary backend HTTP coverage surface.

## If We Return Later

If a future pass hits HTTP-style hangs again, focus first on why sync FastAPI
route execution stalls in the environment, not just on replacing `TestClient`.
