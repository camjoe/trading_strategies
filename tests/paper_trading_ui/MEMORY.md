# UI Backend Test Debug Memory

This note records the regression-sweep investigation around
`tests/paper_trading_ui/test_ui_backend.py`.

## What Failed

During the broader regression sweep, the `tests/paper_trading_ui/test_ui_backend.py`
file appeared to hang instead of failing fast.

The passing neighbor file
`tests/paper_trading_ui/backend/test_account_contract.py` was useful as a contrast:
it does not start the FastAPI app and only tests pure request-to-command mapping
helpers.

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

The hang is not just one broken route in `test_ui_backend.py`.

The evidence points to a framework/runtime issue in this environment around the
sync FastAPI route-dispatch path used by the backend app:

- the failure is broader than one test file
- the failure is broader than Starlette `TestClient` alone
- the minimal async app path succeeds, but the real sync-route app path still stalls

That means a global fixture rewrite is risky, because many UI backend tests rely on
the same `api_client` pattern and a fixture-level workaround could spread a bad
assumption through the whole `tests/paper_trading_ui/` area.

## Important Current State

There is currently a work-in-progress experiment in:

- `tests/paper_trading_ui/conftest.py`
- `tests/paper_trading_ui/test_ui_backend.py`

That experiment replaces `TestClient` with a small sync wrapper over
`httpx.AsyncClient` and `ASGITransport`.

That experiment is not yet the recommended long-term fix. It was useful for
narrowing the failure mode, but it did not resolve the real app hang.

## Recommended Next Step

Do not keep pushing the fixture abstraction yet.

Instead:

1. revert the `api_client` experiment unless it becomes necessary again
2. treat `tests/paper_trading_ui/test_ui_backend.py` as a narrow test-design cleanup
3. rewrite that file to call the route functions directly, because those tests mostly
   assert returned payload dicts and one expected `HTTPException`

This keeps the workaround small and local:

- no broad behavioral change to `tests/paper_trading_ui/conftest.py`
- no accidental impact on the many other UI backend route tests
- the hanging file can still be covered without depending on the broken HTTP client
  path

## If We Return Later

If a future pass wants to fix the HTTP-style backend tests more generally, the next
investigation should focus on why sync FastAPI route execution stalls in this
environment, not just on replacing `TestClient`.
