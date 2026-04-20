"""
Harvester — pulls every video on the ICT YouTube channel, sorts by view count,
saves per-video metadata + transcript JSON, and writes an index.

Usage:
    python harvester.py                   # all videos
    python harvester.py --top-n 20        # top 20 by views (fast validation loop)
    python harvester.py --skip-transcripts  # metadata only

Reads YOUTUBE_API_KEY from companies/ict-research/.env.
ICT channel default: UCtjxa77NqamhVC8atV85Rog (@innercircletrader).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "transcripts"
DEFAULT_CHANNEL_ID = "UCtjxa77NqamhVC8atV85Rog"


def load_api_key() -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        sys.exit(f"missing {env_path} — need YOUTUBE_API_KEY=...")
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("YOUTUBE_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("YOUTUBE_API_KEY not in .env")


def get_uploads_playlist(yt, channel_id: str) -> tuple[str, str]:
    resp = yt.channels().list(part="contentDetails,snippet", id=channel_id).execute()
    if not resp.get("items"):
        sys.exit(f"channel {channel_id} not found")
    item = resp["items"][0]
    return (
        item["contentDetails"]["relatedPlaylists"]["uploads"],
        item["snippet"]["title"],
    )


def list_video_ids(yt, playlist_id: str) -> list[str]:
    ids, page_token = [], None
    while True:
        resp = yt.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        ids.extend(it["contentDetails"]["videoId"] for it in resp["items"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            return ids


def fetch_metadata(yt, video_ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        resp = yt.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(chunk),
        ).execute()
        for it in resp["items"]:
            sn, st = it["snippet"], it.get("statistics", {})
            out.append({
                "video_id": it["id"],
                "title": sn["title"],
                "description": sn.get("description", ""),
                "published_at": sn["publishedAt"],
                "channel_id": sn["channelId"],
                "view_count": int(st.get("viewCount", 0)),
                "like_count": int(st.get("likeCount", 0)),
                "comment_count": int(st.get("commentCount", 0)),
                "duration": it["contentDetails"].get("duration", ""),
            })
    return out


def fetch_transcript(video_id: str) -> tuple[list | None, str]:
    """Return (transcript_list, status). Handles v1.x instance API."""
    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id, languages=["en"])
        snippets = [
            {"text": s.text, "start": s.start, "duration": s.duration}
            for s in fetched
        ]
        return snippets, "ok"
    except TranscriptsDisabled:
        return None, "disabled"
    except NoTranscriptFound:
        return None, "not_found"
    except VideoUnavailable:
        return None, "unavailable"
    except Exception as e:
        return None, f"error: {type(e).__name__}: {e}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    p.add_argument("--top-n", type=int, default=None,
                   help="only process top N videos by view count")
    p.add_argument("--skip-transcripts", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="re-fetch transcripts even if file exists")
    args = p.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    yt = build("youtube", "v3", developerKey=load_api_key())

    print(f"[harvester] channel={args.channel_id}")
    uploads_id, channel_title = get_uploads_playlist(yt, args.channel_id)
    print(f"[harvester] channel_title={channel_title!r} uploads={uploads_id}")

    video_ids = list_video_ids(yt, uploads_id)
    print(f"[harvester] total videos on channel: {len(video_ids)}")

    metadata = fetch_metadata(yt, video_ids)
    metadata.sort(key=lambda v: v["view_count"], reverse=True)

    if args.top_n:
        metadata = metadata[: args.top_n]
        print(f"[harvester] limited to top {args.top_n} by view count")

    index = {
        "channel_id": args.channel_id,
        "channel_title": channel_title,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_videos": len(metadata),
        "videos": [],
    }

    ok_count = 0
    for i, meta in enumerate(metadata, 1):
        vid = meta["video_id"]
        out_path = DATA_DIR / f"{vid}.json"

        if out_path.exists() and not args.force:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            status = existing.get("transcript_status", "unknown")
            print(f"[{i}/{len(metadata)}] {vid} cached ({status}) — {meta['title'][:60]}")
        else:
            if args.skip_transcripts:
                transcript, status = None, "skipped"
            else:
                transcript, status = fetch_transcript(vid)
            record = {**meta, "transcript": transcript, "transcript_status": status}
            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            print(f"[{i}/{len(metadata)}] {vid} {status:12s} views={meta['view_count']:>9d}  {meta['title'][:60]}")

        if status == "ok":
            ok_count += 1

        index["videos"].append({
            "video_id": vid,
            "title": meta["title"],
            "view_count": meta["view_count"],
            "published_at": meta["published_at"],
            "duration": meta["duration"],
            "transcript_status": status,
        })

    index["with_transcripts"] = ok_count
    (DATA_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[harvester] done — {ok_count}/{len(metadata)} transcripts captured")


if __name__ == "__main__":
    try:
        main()
    except HttpError as e:
        sys.exit(f"YouTube API error: {e}")
