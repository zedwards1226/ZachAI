"""
Extractor — Agent 3: convert tagged ICT transcripts into machine-readable
rules JSON via Gemini 2.5 Flash (free tier).

Reads:  data/transcripts/library.json  (from Librarian)
        data/transcripts/<video_id>.json
Writes: data/rules/<setup>__<video_id>.json

Usage:
    python extractor.py                   # all tagged videos
    python extractor.py --limit 5         # top 5 by views (validation loop)
    python extractor.py --setup fair_value_gap --limit 3
    python extractor.py --force           # re-extract even if rules file exists

Reads GEMINI_API_KEY from companies/ict-research/.env.
Free tier on gemini-2.5-flash: 10 RPM, 250 RPD.
"""

import argparse
import json
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_DIR = ROOT / "data" / "transcripts"
RULES_DIR = ROOT / "data" / "rules"
MODEL = "gemini-flash-latest"
MAX_RETRIES = 4

SYSTEM_PROMPT = """You are an expert at reading Inner Circle Trader (ICT) trading transcripts and converting his prose teaching into precise, machine-readable trade rules.

Your job: given a transcript and the primary ICT setup it teaches, output a STRICT JSON object that a backtester can mechanize.

JSON SCHEMA (every field required, use null for unknown, [] for empty list):

{
  "setup_name": "<canonical setup name passed in>",
  "summary": "<1-2 sentence plain-English description of the setup>",
  "timeframe": ["<entry TF, e.g. 1m, 5m, 15m>"],
  "htf_context": ["<higher timeframe conditions that must be true, e.g. 'PDH not swept', 'in discount of weekly dealing range'>"],
  "session_filter": ["<time-of-day filters, e.g. 'NY AM killzone 9:30-11:00 ET', 'London open 02:00-05:00 ET'>"],
  "bias_rules": ["<how to determine long vs short bias>"],
  "entry_conditions": ["<precise mechanical conditions, in order>"],
  "confirmation": ["<optional confirmation signals like MSS, CHoCH, displacement>"],
  "invalidation": "<single clear condition that voids the setup before entry>",
  "stop_loss": "<exact stop placement rule, e.g. 'below FVG low minus 2 ticks'>",
  "take_profit": ["<target rules, in order of priority>"],
  "risk_reward_min": <number or null>,
  "instruments": ["<assets ICT specifies, e.g. 'NQ', 'ES', 'EURUSD', or 'any liquid futures'>"],
  "notes": "<quirks, edge cases, things ICT emphasized>",
  "extraction_confidence": <0.0-1.0 - how mechanizable is this from the transcript>
}

RULES:
- If the transcript is vague/motivational with no concrete rules, set extraction_confidence < 0.4 and fill what you can.
- Prefer ICT's exact language for technical terms (FVG, OB, MSS, killzone, etc.).
- Times default to ET (New York time) unless transcript says otherwise.
- For futures setups assume NQ/ES; for forex assume EURUSD/GBPUSD unless transcript specifies.
- Output ONLY the JSON object."""


def load_api_key() -> str:
    env = ROOT / ".env"
    for line in env.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GEMINI_API_KEY missing from .env")


def load_library() -> dict:
    p = TRANSCRIPTS_DIR / "library.json"
    if not p.exists():
        raise SystemExit(f"missing {p} - run librarian.py first")
    return json.loads(p.read_text(encoding="utf-8"))


def load_transcript(video_id: str) -> dict:
    return json.loads((TRANSCRIPTS_DIR / f"{video_id}.json").read_text(encoding="utf-8"))


def transcript_text(record: dict, max_chars: int = 80_000) -> str:
    if not record.get("transcript"):
        return ""
    text = " ".join(s["text"] for s in record["transcript"])
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[TRANSCRIPT TRUNCATED]"
    return text


def extract_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def call_gemini(client, setup: str, title: str, transcript: str) -> tuple[dict, dict]:
    user_msg = (
        f"Primary ICT setup: {setup}\n"
        f"Video title: {title}\n\n"
        f"=== TRANSCRIPT ===\n{transcript}\n=== END TRANSCRIPT ===\n\n"
        f"Output the rules JSON object now. JSON only."
    )
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.2,
        max_output_tokens=4096,
    )
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=user_msg, config=cfg,
            )
            rules = extract_json(resp.text)
            usage = {
                "prompt_tokens": getattr(resp.usage_metadata, "prompt_token_count", 0),
                "output_tokens": getattr(resp.usage_metadata, "candidates_token_count", 0),
            }
            return rules, usage
        except Exception as e:
            last_err = e
            msg = str(e)
            transient = "503" in msg or "UNAVAILABLE" in msg or "429" in msg
            if not transient or attempt == MAX_RETRIES - 1:
                raise
            backoff = 2 ** attempt * 5  # 5, 10, 20, 40s
            print(f"    retry {attempt+1}/{MAX_RETRIES} after {backoff}s ({msg.split(chr(10))[0][:80]})")
            time.sleep(backoff)
    raise last_err


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--setup", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--rpm-pause", type=float, default=6.5,
                   help="seconds between calls (free tier ~10 RPM)")
    args = p.parse_args()

    RULES_DIR.mkdir(parents=True, exist_ok=True)
    library = load_library()
    client = genai.Client(api_key=load_api_key())

    targets = []
    setups = [args.setup] if args.setup else list(library["by_setup"].keys())
    for setup in setups:
        if setup not in library["by_setup"]:
            print(f"[extractor] no videos for setup '{setup}', skipping")
            continue
        for entry in library["by_setup"][setup]:
            targets.append((setup, entry))
    targets.sort(key=lambda t: t[1]["view_count"], reverse=True)
    if args.limit:
        targets = targets[: args.limit]

    print(f"[extractor] processing {len(targets)} videos with model={MODEL}")

    total_in = total_out = 0
    ok = fail = skipped = 0

    for i, (setup, entry) in enumerate(targets, 1):
        vid = entry["video_id"]
        out_path = RULES_DIR / f"{setup}__{vid}.json"
        if out_path.exists() and not args.force:
            print(f"[{i}/{len(targets)}] {vid} {setup:22s} cached")
            skipped += 1
            continue

        record = load_transcript(vid)
        text = transcript_text(record)
        if not text:
            print(f"[{i}/{len(targets)}] {vid} {setup:22s} no transcript, skipping")
            continue

        try:
            rules, usage = call_gemini(client, setup, record["title"], text)
        except Exception as e:
            msg = str(e).split('\n')[0][:200]
            print(f"[{i}/{len(targets)}] {vid} {setup:22s} FAILED: {type(e).__name__}: {msg}")
            fail += 1
            time.sleep(args.rpm_pause)
            continue

        rules.update({
            "source_video_id": vid,
            "source_title": record["title"],
            "source_view_count": record["view_count"],
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": MODEL,
        })
        out_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                            encoding="utf-8")

        total_in += usage["prompt_tokens"]
        total_out += usage["output_tokens"]
        conf = rules.get("extraction_confidence", "?")
        print(f"[{i}/{len(targets)}] {vid} {setup:22s} ok  conf={conf}  "
              f"in={usage['prompt_tokens']:>5d} out={usage['output_tokens']:>4d}")
        ok += 1

        if i < len(targets):
            time.sleep(args.rpm_pause)

    print(f"\n[extractor] done - ok={ok} skipped={skipped} fail={fail}")
    print(f"[extractor] tokens: input={total_in} output={total_out}")


if __name__ == "__main__":
    main()
