"""
Per-city probability calibration for WeatherAlpha.

Each (city, side) pair accumulates a win rate from resolved trades. A low
historical WR means our ensemble was over-confident for that city/side, so
we shrink the raw ensemble probability further toward the market's implied
probability. A high WR means trust the ensemble more.

Shrinkage factor in [0.0, 0.9]:
  0.0 = trust ensemble fully (WR >= 70%)
  0.9 = trust market almost fully (WR == 0)

With small samples we apply a Bayesian prior pulling toward 50% WR so the
factor doesn't swing wildly off a 2-trade sample.
"""
import logging
import sqlite3
import time
from pathlib import Path

from config import (
    DATABASE_PATH,
    PROB_SHRINK_TO_MARKET,
    CALIBRATION_MIN_SAMPLE,
    CALIBRATION_PRIOR_WEIGHT,
)

log = logging.getLogger(__name__)

# In-process cache; refresh every hour so new resolutions flow in daily.
_CACHE: dict[tuple[str, str], float] = {}
_CACHE_TS: float = 0.0
_CACHE_TTL_SECS = 3600


def _db_path() -> Path:
    p = Path(DATABASE_PATH)
    if not p.is_absolute():
        p = Path(__file__).parent / p
    return p


def _refresh_cache() -> None:
    """Rebuild per-city-side shrinkage factors from the trades table."""
    global _CACHE, _CACHE_TS
    _CACHE = {}
    try:
        conn = sqlite3.connect(str(_db_path()))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT city, side, COUNT(*) AS n,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) AS wins
            FROM trades
            WHERE resolved_at IS NOT NULL
            GROUP BY city, side
            """
        ).fetchall()
        conn.close()
    except Exception as exc:
        log.warning("Calibration refresh failed, using global default: %s", exc)
        _CACHE_TS = time.time()
        return

    for r in rows:
        n = r["n"]
        if n < CALIBRATION_MIN_SAMPLE:
            continue  # fall back to global default
        # Bayesian-smoothed WR: pull toward 0.5 by CALIBRATION_PRIOR_WEIGHT.
        smoothed_wr = (r["wins"] + 0.5 * CALIBRATION_PRIOR_WEIGHT) / (
            n + CALIBRATION_PRIOR_WEIGHT
        )
        # Map WR -> shrinkage. WR 0.7+ = 0.05 shrink (trust ensemble),
        # WR 0.3- = 0.75 shrink (trust market). Linear between.
        shrink = max(0.05, min(0.9, 0.95 - 1.4 * smoothed_wr))
        _CACHE[(r["city"], r["side"].upper())] = round(shrink, 3)

    _CACHE_TS = time.time()
    if _CACHE:
        log.info(
            "Calibration refreshed: %s",
            ", ".join(f"{k[0]}/{k[1]}={v}" for k, v in sorted(_CACHE.items())),
        )


def get_shrinkage(city: str, side: str) -> float:
    """
    Return per-(city, side) probability shrinkage in [0.05, 0.9].
    Falls back to the global PROB_SHRINK_TO_MARKET when sample is too small.
    """
    if time.time() - _CACHE_TS > _CACHE_TTL_SECS:
        _refresh_cache()
    return _CACHE.get((city, side.upper()), PROB_SHRINK_TO_MARKET)


def dump_table() -> list[dict]:
    """Return the current shrinkage table for /api/calibration debugging."""
    if time.time() - _CACHE_TS > _CACHE_TTL_SECS:
        _refresh_cache()
    return [
        {"city": k[0], "side": k[1], "shrinkage": v}
        for k, v in sorted(_CACHE.items())
    ]
