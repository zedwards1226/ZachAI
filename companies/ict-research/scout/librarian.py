"""
Librarian — Agent 2: tag every harvested transcript by ICT setup name,
group by primary setup, dedupe within each group by view count.

Reads:  data/transcripts/<video_id>.json + index.json  (from Harvester)
Writes: data/transcripts/library.json

Usage:
    python librarian.py
    python librarian.py --min-hits 3   # require >=3 keyword hits to tag
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "transcripts"

# ICT setup taxonomy. Each setup = (canonical_name, list of regex patterns).
# Patterns are case-insensitive. Word boundaries enforced where it matters.
SETUPS = {
    "silver_bullet": [
        r"\bsilver bullet\b",
        r"\b10[: ]?00\s*(am|a\.m\.)\b.*\b11[: ]?00\b",
    ],
    "order_block": [
        r"\border block\b",
        r"\bbullish ob\b",
        r"\bbearish ob\b",
        r"\bmitigation block\b",
    ],
    "fair_value_gap": [
        r"\bfair value gap\b",
        r"\bfvg\b",
        r"\binversion fvg\b",
        r"\bivfg\b",
        r"\bbalanced price range\b",
    ],
    "liquidity_grab": [
        r"\bliquidity grab\b",
        r"\bstop hunt\b",
        r"\brun on liquidity\b",
        r"\bsell[- ]side liquidity\b",
        r"\bbuy[- ]side liquidity\b",
        r"\bliquidity pool\b",
    ],
    "breaker_block": [
        r"\bbreaker block\b",
        r"\bbreaker\b",
    ],
    "ote": [
        r"\boptimal trade entry\b",
        r"\bote\b",
        r"\b62\b.*\b79\b",
        r"\b0\.62\b.*\b0\.79\b",
    ],
    "market_structure_shift": [
        r"\bmarket structure shift\b",
        r"\bmss\b",
        r"\bchange of character\b",
        r"\bchoch\b",
        r"\bbos\b",
        r"\bbreak of structure\b",
    ],
    "power_of_three": [
        r"\bpower of (?:three|3)\b",
        r"\bpo3\b",
        r"\baccumulation.*manipulation.*distribution\b",
        r"\bamd\b",
    ],
    "killzone": [
        r"\bkill ?zone\b",
        r"\blondon (open|kill)\b",
        r"\bnew york (open|kill)\b",
        r"\basian range\b",
    ],
    "judas_swing": [
        r"\bjudas swing\b",
    ],
    "turtle_soup": [
        r"\bturtle soup\b",
    ],
    "premium_discount": [
        r"\bpremium\b.*\bdiscount\b",
        r"\bequilibrium\b",
        r"\bdealing range\b",
    ],
    "smt_divergence": [
        r"\bsmt divergence\b",
        r"\bsmart money tool\b",
        r"\bsmt\b",
    ],
    "previous_high_low": [
        r"\bprevious day('?s)? high\b",
        r"\bprevious day('?s)? low\b",
        r"\bpdh\b",
        r"\bpdl\b",
        r"\basian (high|low)\b",
    ],
}

COMPILED = {
    name: [re.compile(p, re.IGNORECASE) for p in patterns]
    for name, patterns in SETUPS.items()
}


def transcript_text(record: dict) -> str:
    if not record.get("transcript"):
        return ""
    return " ".join(s["text"] for s in record["transcript"])


def score_setups(title: str, transcript: str) -> dict[str, int]:
    """Return {setup_name: hit_count}. Title hits weighted 3x."""
    hits = {}
    for setup, patterns in COMPILED.items():
        title_hits = sum(len(p.findall(title)) for p in patterns)
        body_hits = sum(len(p.findall(transcript)) for p in patterns)
        score = title_hits * 3 + body_hits
        if score:
            hits[setup] = score
    return hits


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--min-hits", type=int, default=2,
                   help="minimum score to tag a setup (default 2)")
    args = p.parse_args()

    index_path = DATA_DIR / "index.json"
    if not index_path.exists():
        raise SystemExit(f"missing {index_path} — run harvester.py first")
    index = json.loads(index_path.read_text(encoding="utf-8"))

    tagged = []
    for entry in index["videos"]:
        if entry["transcript_status"] != "ok":
            continue
        vid_path = DATA_DIR / f"{entry['video_id']}.json"
        if not vid_path.exists():
            continue
        record = json.loads(vid_path.read_text(encoding="utf-8"))
        scores = score_setups(record["title"], transcript_text(record))
        scores = {k: v for k, v in scores.items() if v >= args.min_hits}
        if not scores:
            continue
        primary = max(scores, key=scores.get)
        tagged.append({
            "video_id": record["video_id"],
            "title": record["title"],
            "view_count": record["view_count"],
            "published_at": record["published_at"],
            "duration": record.get("duration", ""),
            "primary_setup": primary,
            "setup_scores": dict(sorted(scores.items(),
                                        key=lambda kv: kv[1], reverse=True)),
        })

    untagged = [
        v for v in index["videos"]
        if v["transcript_status"] == "ok"
        and v["video_id"] not in {t["video_id"] for t in tagged}
    ]

    by_setup = defaultdict(list)
    for t in tagged:
        by_setup[t["primary_setup"]].append(t)
    for setup in by_setup:
        by_setup[setup].sort(key=lambda v: v["view_count"], reverse=True)

    counts = Counter(t["primary_setup"] for t in tagged)

    library = {
        "channel_id": index["channel_id"],
        "channel_title": index["channel_title"],
        "source_index_fetched_at": index["fetched_at"],
        "min_hits": args.min_hits,
        "total_with_transcripts": index.get("with_transcripts", 0),
        "total_tagged": len(tagged),
        "total_untagged": len(untagged),
        "setup_counts": dict(counts.most_common()),
        "by_setup": {k: by_setup[k] for k in counts},
        "untagged": [{"video_id": v["video_id"], "title": v["title"],
                      "view_count": v["view_count"]} for v in untagged],
    }

    out = DATA_DIR / "library.json"
    out.write_text(json.dumps(library, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    print(f"[librarian] tagged {len(tagged)}/{index.get('with_transcripts', 0)} videos")
    print(f"[librarian] untagged: {len(untagged)}")
    print("[librarian] setup distribution:")
    for setup, n in counts.most_common():
        print(f"  {setup:24s} {n:3d}")
    print(f"[librarian] wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
