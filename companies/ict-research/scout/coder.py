"""
Coder — Agent 4: take a rules JSON and generate a Python strategy file
that the Backtester can run.

Reads:  data/rules/<setup>__<video_id>.json
        forge/primitives.py            (provides building blocks)
Writes: forge/strategies/<setup>__<video_id>.py

Each generated strategy must expose:
    def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
        # df has columns ['open','high','low','close','volume'] and an ET tz index.
        # returns df + columns ['signal','entry','stop','target'] where
        # signal in {1, -1, 0}, prices NaN where signal==0.

Validation: ast-parse, import, smoke-test on synthetic OHLCV.

Usage:
    python coder.py                       # all rules files
    python coder.py --limit 3
    python coder.py --rules-file fair_value_gap__XN8tuO4QIRw.json
    python coder.py --force
"""

import argparse
import ast
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "data" / "rules"
STRATEGY_DIR = ROOT / "forge" / "strategies"
PRIMITIVES_PATH = ROOT / "forge" / "primitives.py"
MODEL = "gemini-flash-latest"
MAX_RETRIES = 4

PRIMITIVES_API = """\
forge.primitives provides:

  in_session(df, name) -> bool Series
    valid names: 'asia', 'london_open', 'ny_am', 'ny_am_kz', 'ny_lunch',
    'ny_pm', 'silver_bullet_am' (10:00-11:00 ET), 'silver_bullet_pm' (14:00-15:00 ET).

  swing_high(df, lookback=3) -> bool Series
  swing_low(df, lookback=3) -> bool Series

  detect_fvg(df) -> DataFrame with columns:
    bull_fvg (bool), bull_fvg_low (gap bottom), bull_fvg_high (gap top),
    bear_fvg (bool), bear_fvg_low, bear_fvg_high
    (3-candle FVG: bull when low[i] > high[i-2])

  detect_order_block(df, displacement_atr_mult=1.5, atr_period=14) -> DataFrame:
    bull_ob (bool), bull_ob_low, bull_ob_high,
    bear_ob (bool), bear_ob_low, bear_ob_high
    (last opposite-color candle before a displacement bar)

  liquidity_sweep_high(df, level: Series) -> bool Series
  liquidity_sweep_low(df, level: Series) -> bool Series

  market_structure_shift(df, lookback=3) -> DataFrame:
    bull_mss (bool), bear_mss (bool)
    (close breaks last swing high/low)

  previous_day_levels(df) -> DataFrame: pdh, pdl (forward-filled)

  empty_signals(df) -> DataFrame with columns
    ['signal', 'entry', 'stop', 'target'] (signal=0, prices=NaN). Start here.
"""

SYSTEM_PROMPT = f"""You are an expert Python developer specializing in quantitative trading strategies. You translate ICT (Inner Circle Trader) rules JSON into a working pandas-based backtest function.

You MUST:
1. Output ONLY valid Python source code. No markdown fences. No prose. No comments outside the code. No trailing triple-quotes.
2. Define exactly one public function: `def generate_signals(df: pd.DataFrame) -> pd.DataFrame`.
3. Bar columns are LOWERCASE: 'open', 'high', 'low', 'close', 'volume'. NEVER use 'High', 'Open', etc.
4. Import from `forge.primitives` for ICT building blocks (do NOT reinvent them).
5. Use vectorized pandas/numpy where reasonable; explicit for-loops only when state across bars is required.
6. Return a DataFrame with the SAME index as `df` and these EXACT columns:
   - `signal` (int): 1 long, -1 short, 0 flat (one entry per setup, no pyramiding)
   - `entry` (float): entry price, NaN where signal==0
   - `stop` (float): stop-loss price, NaN where signal==0
   - `target` (float): take-profit price, NaN where signal==0
7. Apply session_filter using `in_session()` if the rules specify time-of-day.
8. Apply HTF/bias context as best you can with the bars you have. If rules require HTF data you don't have, document the assumption in a single comment line at the top of the function.
9. Keep it deterministic — no random, no IO, no external API calls.
10. Use sensible default risk/reward if rules don't specify one (e.g. 1:2).

PRIMITIVE API REFERENCE:
{PRIMITIVES_API}

REQUIRED FILE STRUCTURE:

\"\"\"<setup_name> from <source_title>\"\"\"
from __future__ import annotations
import pandas as pd
import numpy as np
from forge.primitives import (
    # import only what you actually use
)


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    out = empty_signals(df)
    # ... your logic here
    return out


Output the strategy file content NOW. Python only, no fences."""


def load_api_key() -> str:
    env = ROOT / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GEMINI_API_KEY missing from .env")


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:python|py)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Strip stray trailing triple-quote (common LLM artifact closing the
    # file-level docstring as if it were an unclosed multi-line string).
    lines = text.rstrip().split("\n")
    while lines and lines[-1].strip() == '"""':
        lines.pop()
    return "\n".join(lines)


def call_gemini(client, rules: dict) -> tuple[str, dict]:
    user_msg = (
        f"Rules JSON to translate:\n\n"
        f"{json.dumps(rules, indent=2, ensure_ascii=False)}\n\n"
        f"Output the complete Python strategy file content."
    )
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=8192,
    )
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(model=MODEL, contents=user_msg, config=cfg)
            code = strip_fences(resp.text)
            usage = {
                "prompt_tokens": getattr(resp.usage_metadata, "prompt_token_count", 0),
                "output_tokens": getattr(resp.usage_metadata, "candidates_token_count", 0),
            }
            return code, usage
        except Exception as e:
            last = e
            msg = str(e)
            transient = "503" in msg or "UNAVAILABLE" in msg or "429" in msg
            if not transient or attempt == MAX_RETRIES - 1:
                raise
            backoff = 2 ** attempt * 5
            print(f"    retry {attempt+1}/{MAX_RETRIES} after {backoff}s")
            time.sleep(backoff)
    raise last


def validate_code(code: str) -> tuple[bool, str]:
    """Return (ok, reason). Checks: parses, has generate_signals, no obvious banned ops."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    has_func = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "generate_signals":
            has_func = True
            break
    if not has_func:
        return False, "missing generate_signals function"

    banned = ["requests.", "urllib", "subprocess", "open(", "input(", "exec(", "eval("]
    for b in banned:
        if b in code:
            return False, f"banned operation: {b}"
    return True, "ok"


def smoke_test(strategy_path: Path) -> tuple[bool, str]:
    """Import the strategy module and call generate_signals on synthetic bars."""
    try:
        # Make ROOT importable so `from forge.primitives import ...` works
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        spec = importlib.util.spec_from_file_location(
            f"strat_{strategy_path.stem}", strategy_path
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Synthetic 2-day intraday dataset
        idx = pd.date_range("2025-01-02 09:30", periods=240, freq="1min", tz="US/Eastern")
        rng = np.random.default_rng(0)
        close = 5000 + np.cumsum(rng.standard_normal(240) * 2)
        df = pd.DataFrame({
            "open": close - rng.standard_normal(240),
            "high": close + rng.random(240) * 3,
            "low":  close - rng.random(240) * 3,
            "close": close,
            "volume": rng.integers(100, 1000, 240),
        }, index=idx)
        # Ensure high>=max(open,close), low<=min(open,close)
        df["high"] = df[["high", "open", "close"]].max(axis=1)
        df["low"]  = df[["low",  "open", "close"]].min(axis=1)

        result = mod.generate_signals(df)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if not isinstance(result, pd.DataFrame):
        return False, f"returned {type(result).__name__}, expected DataFrame"
    if not result.index.equals(df.index):
        return False, "index does not match input"
    for col in ("signal", "entry", "stop", "target"):
        if col not in result.columns:
            return False, f"missing column {col!r}"
    valid_signals = result["signal"].isin([-1, 0, 1]).all()
    if not valid_signals:
        return False, f"signal contains values outside {{-1,0,1}}"
    return True, f"ok, {int((result['signal'] != 0).sum())} signals on synthetic data"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--rules-file", default=None,
                   help="just one specific rules file (basename)")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)

    if args.rules_file:
        rules_paths = [RULES_DIR / args.rules_file]
    else:
        rules_paths = sorted(RULES_DIR.glob("*.json"),
                             key=lambda p: -json.loads(p.read_text(encoding="utf-8"))
                                            .get("source_view_count", 0))
    if args.limit:
        rules_paths = rules_paths[: args.limit]

    print(f"[coder] processing {len(rules_paths)} rules files with model={MODEL}")
    client = genai.Client(api_key=load_api_key())

    ok = fail = skipped = 0
    for i, rp in enumerate(rules_paths, 1):
        out_path = STRATEGY_DIR / (rp.stem + ".py")
        if out_path.exists() and not args.force:
            print(f"[{i}/{len(rules_paths)}] {rp.stem} cached")
            skipped += 1
            continue

        rules = json.loads(rp.read_text(encoding="utf-8"))
        try:
            code, usage = call_gemini(client, rules)
        except Exception as e:
            print(f"[{i}/{len(rules_paths)}] {rp.stem} CALL_FAILED: {type(e).__name__}: {str(e)[:120]}")
            fail += 1
            continue

        valid, reason = validate_code(code)
        if not valid:
            print(f"[{i}/{len(rules_paths)}] {rp.stem} INVALID: {reason}")
            (STRATEGY_DIR / f"{rp.stem}.invalid.py").write_text(code, encoding="utf-8")
            fail += 1
            time.sleep(6.5)
            continue

        out_path.write_text(code, encoding="utf-8")

        smoke_ok, smoke_msg = smoke_test(out_path)
        if not smoke_ok:
            print(f"[{i}/{len(rules_paths)}] {rp.stem} SMOKE_FAIL: {smoke_msg}")
            out_path.rename(STRATEGY_DIR / f"{rp.stem}.smoke_failed.py")
            fail += 1
        else:
            print(f"[{i}/{len(rules_paths)}] {rp.stem} ok  in={usage['prompt_tokens']} out={usage['output_tokens']}  smoke: {smoke_msg}")
            ok += 1
        time.sleep(6.5)

    print(f"\n[coder] done — ok={ok} skipped={skipped} fail={fail}")


if __name__ == "__main__":
    main()
