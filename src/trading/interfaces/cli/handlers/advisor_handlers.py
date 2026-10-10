"""Handlers for the advisor ledger, digest, scoring, and scorecard commands."""

from __future__ import annotations

from datetime import date
from functools import partial

from backtesting.composition import run_backtest_metrics_only
from trading.interfaces.cli.handlers.context import CliContext
from trading.services.advisor.decisions import record_decision
from trading.services.advisor.digest import build_advisor_digest
from trading.services.advisor.presentation import (
    render_advisor_digest_lines,
    render_scorecard_lines,
    render_scoring_lines,
)
from trading.services.advisor.scorecard import build_advisor_scorecard
from trading.services.advisor.scoring import score_due_decisions


def _parse_notes(raw_notes: list[str]) -> dict[str, str]:
    notes: dict[str, str] = {}
    for raw in raw_notes:
        key, separator, value = raw.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"--note must be KEY=VALUE, got '{raw}'")
        notes[key.strip()] = value.strip()
    return notes


def handle_advisor_record(conn, args, parser, *, ctx: CliContext) -> None:
    try:
        decision_id = record_decision(
            conn,
            account_name=args.account,
            decision_type=args.type,
            rationale=args.rationale,
            decided_by=args.decided_by,
            book_name=args.book,
            strategy_key=args.strategy,
            alternative_strategy_key=args.alternative,
            notes=_parse_notes(args.note),
            optimization_experiment_id=args.experiment_id,
            promotion_review_id=args.promotion_review_id,
            outcome_window_days=args.window_days,
        )
    except ValueError as error:
        parser.error(str(error))
        return
    print(
        f"Recorded decision #{decision_id} ({args.type}) for {args.account}; scored after {args.window_days} trading days."
    )


def handle_advisor_digest(conn, args, parser, *, ctx: CliContext) -> None:
    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else None
        digest = build_advisor_digest(conn, account_name=args.account, as_of=as_of)
    except ValueError as error:
        parser.error(str(error))
        return
    print("\n".join(render_advisor_digest_lines(digest)))


def handle_advisor_score(conn, args, parser, *, ctx: CliContext) -> None:
    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else None
        results = score_due_decisions(
            conn,
            run_backtest_fn=partial(run_backtest_metrics_only, provider=ctx.provider),
            account_name=args.account,
            as_of=as_of,
        )
    except ValueError as error:
        parser.error(str(error))
        return
    print("\n".join(render_scoring_lines(results)))


def handle_advisor_scorecard(conn, args, parser, *, ctx: CliContext) -> None:
    try:
        scorecard = build_advisor_scorecard(conn, account_name=args.account, group_by=args.by)
    except ValueError as error:
        parser.error(str(error))
        return
    print("\n".join(render_scorecard_lines(scorecard)))
