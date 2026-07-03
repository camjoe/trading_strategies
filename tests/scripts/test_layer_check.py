from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.checks.layer_check import (
    BANNED_PATH_RULES,
    LAYER_RULES,
    BannedPathRule,
    LayerRule,
    check_banned_path_rule,
    check_rule,
    run_layer_check,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_script(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.checks.layer_check", "--repo-root", str(repo)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Integration test — real repo must be clean
# ---------------------------------------------------------------------------


def test_layer_check_passes_on_real_repo() -> None:
    """The actual codebase must have zero layer violations."""
    result = run_layer_check(repo_root=PROJECT_ROOT)
    assert result == 0


# ---------------------------------------------------------------------------
# Unit tests for check_rule logic
# ---------------------------------------------------------------------------


def _write_py(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


def test_check_rule_detects_forbidden_import(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "bad.py", "from trading.database.init import ensure_db\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
    )
    violations = check_rule(tmp_path, rule)
    assert len(violations) == 1
    assert violations[0].import_text == "trading.database.init"
    assert violations[0].rule_label == "test-rule"


def test_check_rule_allows_non_forbidden_import(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "ok.py", "from trading.repositories.accounts import fetch_accounts\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
    )
    violations = check_rule(tmp_path, rule)
    assert violations == []


def test_check_rule_honours_exceptions(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "db.py", "from trading.database.init import ensure_db\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
        exceptions=("services/db.py",),
    )
    violations = check_rule(tmp_path, rule)
    assert violations == []


def test_check_rule_honours_excluded_prefixes(tmp_path: Path) -> None:
    allowed = tmp_path / "src" / "infrastructure" / "brokers"
    disallowed = tmp_path / "src" / "infrastructure" / "database"
    allowed.mkdir(parents=True)
    disallowed.mkdir(parents=True)
    _write_py(allowed, "adapter.py", "import ib_async\n")
    _write_py(disallowed, "config.py", "import ib_async\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="src/infrastructure/**/*.py",
        forbidden_prefixes=("ib_async",),
        excluded_prefixes=("src/infrastructure/brokers/",),
    )

    violations = check_rule(tmp_path, rule)

    assert len(violations) == 1
    assert violations[0].file.name == "config.py"


def test_check_rule_skips_syntax_errors_gracefully(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "broken.py", "def (:\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
    )
    violations = check_rule(tmp_path, rule)
    assert violations == []


# ---------------------------------------------------------------------------
# Market-data adapter boundary rule
# ---------------------------------------------------------------------------


def _market_data_rule() -> LayerRule:
    rule = next(
        (r for r in LAYER_RULES if r.forbidden_prefixes == ("infrastructure.market_data.",)),
        None,
    )
    assert rule is not None, "Expected a layer rule forbidding infrastructure.market_data imports in src/trading"
    return rule


def test_trading_must_not_import_market_data_adapter(tmp_path: Path) -> None:
    src = tmp_path / "src" / "trading" / "services" / "pricing"
    src.mkdir(parents=True)
    _write_py(src, "lookups.py", "from infrastructure.market_data.factory import build_provider\n")

    violations = check_rule(tmp_path, _market_data_rule())
    assert len(violations) == 1
    assert violations[0].import_text == "infrastructure.market_data.factory"


def test_backtest_seam_may_import_market_data_adapter(tmp_path: Path) -> None:
    seam = tmp_path / "src" / "trading" / "backtesting"
    seam.mkdir(parents=True)
    _write_py(seam, "backtest.py", "from infrastructure.market_data.factory import build_provider\n")

    violations = check_rule(tmp_path, _market_data_rule())
    assert violations == []


# ---------------------------------------------------------------------------
# SDK ownership and retired package rules
# ---------------------------------------------------------------------------


def _rule_with_label(label: str) -> LayerRule:
    rule = next((r for r in LAYER_RULES if r.label == label), None)
    assert rule is not None, f"Expected layer rule {label!r}"
    return rule


def test_trading_must_not_import_broker_sdk(tmp_path: Path) -> None:
    src = tmp_path / "src" / "trading" / "services"
    src.mkdir(parents=True)
    _write_py(src, "broker.py", "import ib_async\n")

    violations = check_rule(tmp_path, _rule_with_label("trading → no direct broker SDK imports"))

    assert len(violations) == 1
    assert violations[0].import_text == "ib_async"


def test_broker_infrastructure_may_import_broker_sdk(tmp_path: Path) -> None:
    brokers = tmp_path / "src" / "infrastructure" / "brokers"
    brokers.mkdir(parents=True)
    _write_py(brokers, "adapter.py", "import ib_async\n")

    violations = check_rule(
        tmp_path,
        _rule_with_label("non-broker infrastructure → no direct broker SDK imports"),
    )

    assert violations == []


def test_trading_must_not_import_external_data_sdk(tmp_path: Path) -> None:
    src = tmp_path / "src" / "trading" / "domain"
    src.mkdir(parents=True)
    _write_py(src, "signals.py", "from pytrends.request import TrendReq\n")

    violations = check_rule(tmp_path, _rule_with_label("trading → no direct external-data SDK imports"))

    assert len(violations) == 1
    assert violations[0].import_text == "pytrends.request"


def test_feature_provider_infrastructure_may_import_external_data_sdk(tmp_path: Path) -> None:
    providers = tmp_path / "src" / "infrastructure" / "feature_providers"
    providers.mkdir(parents=True)
    _write_py(providers, "social.py", "import praw\n")

    violations = check_rule(
        tmp_path,
        _rule_with_label("non-feature-provider infrastructure → no direct external-data SDK imports"),
    )

    assert violations == []


def test_runtime_settings_package_reintroduction_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "src" / "trading" / "services" / "runtime_settings"
    path.mkdir(parents=True)
    rule = BannedPathRule(
        label="test-banned-path",
        banned_paths=("src/trading/services/runtime_settings",),
    )

    violations = check_banned_path_rule(tmp_path, rule)

    assert len(violations) == 1
    assert violations[0].path == path


def test_real_banned_path_rules_are_present() -> None:
    banned = {
        rel_path
        for rule in BANNED_PATH_RULES
        for rel_path in rule.banned_paths
    }

    assert "src/trading/services/runtime_settings" in banned
    assert "src/trading/services/runtime_throttle" in banned


# ---------------------------------------------------------------------------
# CLI exit-code tests
# ---------------------------------------------------------------------------


def test_cli_exits_zero_when_no_violations(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "clean.py", "import os\n")

    rule_glob_dir = tmp_path / "apps" / "paper_trading_web" / "backend" / "services"
    rule_glob_dir.mkdir(parents=True)

    result = _run_script(tmp_path)
    assert result.returncode == 0
    assert "passed" in result.stdout


def test_cli_exits_one_when_violations_present(tmp_path: Path) -> None:
    bad_dir = tmp_path / "apps" / "paper_trading_web" / "backend" / "routes"
    bad_dir.mkdir(parents=True)
    _write_py(bad_dir, "bad.py", "from infrastructure.database.init import ensure_db\n")

    result = _run_script(tmp_path)
    assert result.returncode == 1
    assert "FAILED" in result.stdout
