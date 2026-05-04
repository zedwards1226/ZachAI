"""Apply backtest sweep results to live bands.

Architecture: bands live in TWO places.
  1. main.py defaults — the original calibrated bands, never touched
     by automation. This is the seed.
  2. state/strategy_bands.json — overrides written by tune_all().
     Read at startup; if missing or unreadable, fall back to defaults.

This separation means:
  - On a fresh box (no JSON), bot uses the safe seed bands
  - tune_all() writes JSON only when sweep finds a winner; otherwise
    JSON stays at the previous good state
  - Operator can clear `state/strategy_bands.json` to force a "factory
    reset" back to main.py defaults
  - Every band change is an audit log entry in band_history.jsonl

No SQL schema added — bands are config, not trade data. JSON is the
right shape.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backtest.band_sweep import sweep_strategy
from config import BASE_DIR

logger = logging.getLogger(__name__)

BANDS_FILE = BASE_DIR / "state" / "strategy_bands.json"
HISTORY_FILE = BASE_DIR / "state" / "band_history.jsonl"


def load_band_overrides() -> dict[str, dict]:
    """Read live overrides keyed by strategy name. Returns empty dict
    if file missing or unreadable. Format:
        {
          "crypto_btc15m_midband": {
            "no_bands": [[0.20, 0.30, 0.15]],
            "yes_bands": [[0.75, 0.85, 0.90]],
            "updated_at": "...",
            "source": "sweep_2026-05-04"
          },
          ...
        }
    """
    if not BANDS_FILE.exists():
        return {}
    try:
        return json.loads(BANDS_FILE.read_text())
    except Exception as e:
        logger.warning("Could not load %s: %s — falling back to defaults",
                       BANDS_FILE, e)
        return {}


def apply_overrides_to_strategy(strategy, overrides: dict) -> None:
    """Mutate a CryptoMidBandStrategy in place to use override bands.
    Tuples-of-lists are tolerated (JSON has no tuples) by converting on read."""
    if "no_bands" in overrides:
        strategy._no_bands = [tuple(b) for b in overrides["no_bands"]]
    if "yes_bands" in overrides:
        strategy._yes_bands = [tuple(b) for b in overrides["yes_bands"]]


def _append_history(record: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def tune_all(registry: dict[str, list[tuple]]) -> dict:
    """Run band sweep across every strategy in the registry. Persist
    winners to BANDS_FILE. Returns a summary dict for logging."""
    now = datetime.now(timezone.utc).isoformat()
    overrides = load_band_overrides()
    summary: dict = {"ts": now, "by_strategy": {}, "applied": [], "kept": []}

    for sector, entries in registry.items():
        for strategy, series_ticker in entries:
            no_only = (not strategy._yes_bands)  # preserve NO-only strategies
            try:
                result = sweep_strategy(strategy, series_ticker, no_only=no_only)
            except Exception as e:
                logger.exception("sweep failed for %s: %s", strategy.name, e)
                summary["by_strategy"][strategy.name] = {"error": str(e)[:200]}
                continue

            entry = {
                "baseline_pnl": result["baseline"]["pnl"],
                "baseline_winrate": result["baseline"]["winrate"],
                "baseline_trades": result["baseline"]["trades"],
                "best_pnl": result["best"]["pnl"],
                "best_winrate": result["best"]["winrate"],
                "best_trades": result["best"]["trades"],
                "changed": result["changed"],
            }

            if result["changed"]:
                # Stage the override
                overrides[strategy.name] = {
                    "no_bands": [list(b) for b in result["best"]["no_bands"]],
                    "yes_bands": [list(b) for b in result["best"]["yes_bands"]],
                    "updated_at": now,
                    "source": f"sweep_{now[:10]}",
                    "backtest_pnl": result["best"]["pnl"],
                    "backtest_winrate": result["best"]["winrate"],
                    "backtest_trades": result["best"]["trades"],
                }
                summary["applied"].append(strategy.name)
                _append_history({
                    "ts": now,
                    "strategy": strategy.name,
                    "series_ticker": series_ticker,
                    "old_no_bands": [list(b) for b in result["baseline"]["no_bands"]],
                    "old_yes_bands": [list(b) for b in result["baseline"]["yes_bands"]],
                    "new_no_bands": [list(b) for b in result["best"]["no_bands"]],
                    "new_yes_bands": [list(b) for b in result["best"]["yes_bands"]],
                    "old_pnl": result["baseline"]["pnl"],
                    "new_pnl": result["best"]["pnl"],
                    "old_winrate": result["baseline"]["winrate"],
                    "new_winrate": result["best"]["winrate"],
                    "trades_in_test": result["best"]["trades"],
                })
                logger.info(
                    "TUNE %s: pnl $%+.0f -> $%+.0f, winrate %.1f%% -> %.1f%%, "
                    "no=%s yes=%s",
                    strategy.name,
                    result["baseline"]["pnl"], result["best"]["pnl"],
                    result["baseline"]["winrate"] * 100,
                    result["best"]["winrate"] * 100,
                    result["best"]["no_bands"],
                    result["best"]["yes_bands"],
                )
            else:
                summary["kept"].append(strategy.name)
                logger.info("KEEP %s: backtest doesn't beat baseline",
                            strategy.name)

            summary["by_strategy"][strategy.name] = entry

    # Persist all overrides at once
    if summary["applied"]:
        BANDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        BANDS_FILE.write_text(json.dumps(overrides, indent=2))
        logger.info("Wrote %d override(s) to %s", len(summary["applied"]), BANDS_FILE)

    return summary
