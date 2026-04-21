# wpflow — 75-second Launch Demo Script

**Length target:** 75 seconds (60 absolute minimum, 90 hard ceiling).
**Host:** Loom free tier (native 1080p, direct "download mp4" + embed link).
**Upload to:** YouTube Unlisted (for the Show HN + MCPize listing embed), mirror on Twitter/X (native upload).
**Title (YouTube / filename):** `wpflow demo — Claude bulk-updates 100 WordPress posts in 75 seconds`

---

## Why this specific demo

Three things happen in one take:
1. The **"past developer left the codebase in rough shape"** buyer (DEMAND_SIGNALS Signal 4) sees wpflow solve the exact pain they named.
2. The **"MCPs dump megabytes of context"** skeptic (DEMAND_SIGNALS Signal 9) sees a 100-post operation that doesn't blow up the context window.
3. The **"I keep trying, but I always fail"** host-compatibility worry (Signal 3) is defused by watching it just work.

Every second of this demo is load-bearing. Don't pad it, don't cut it.

---

## Setup (before recording)

- **Screen:** 1920x1080. Claude Desktop maximized. Hide taskbar. Close every unrelated window.
- **Browser tab:** open `https://<your-demo-site>/wp-admin/edit.php?show_sticky=1` in Chrome on the second monitor (for the "before/after tag count" reveal).
- **Claude Desktop:** conversation pre-loaded with the user message below typed (not sent) so the first keystroke on camera is `Enter`.
- **Audio:** no voiceover. Background silent. Type sounds stay on — they're rhythm.
- **Mouse:** large cursor (Windows → Ease of Access → Cursor & pointer size: 3).
- **Font:** Claude Desktop at 110% zoom (`Ctrl +` once).

---

## Beat sheet (75 seconds)

| Time | What's on screen | Action |
|---|---|---|
| 0:00 – 0:03 | Claude Desktop empty chat. wpflow icon visible in the tools sidebar. | Title card overlay: **"wpflow — 75 seconds to clean up 100 WordPress posts"** |
| 0:03 – 0:08 | Chat with the pre-typed user prompt already visible. | User message visible: *"Using wpflow: list all published posts, find any with zero tags, suggest a tag from each post's title, and update them. Show me the count before and after."* |
| 0:08 – 0:09 | Press `Enter`. | Message sends. |
| 0:09 – 0:22 | Claude's tool calls stream. Zoom in once on the first tool call header: `list_posts(per_page=100)`. | Overlay annotation on the tool result: *"Returned 100 posts in 1.8 KB — excerpts only, no body HTML."* |
| 0:22 – 0:28 | Claude says "42 posts have zero tags. I'll suggest a tag from each title and update them." | Overlay on the message: *"Claude picked the workflow. No prompt-engineering tricks."* |
| 0:28 – 0:55 | Stream of `update_post(..., tags=[...])` calls — time-compressed to 1.5× if needed to fit. | Small counter overlay bottom-right: *"Posts tagged: 1 / 42 → 42 / 42"* |
| 0:55 – 1:04 | Cut to wp-admin tab. Filter "no tags" — result is empty. Back to Claude's final summary. | Overlay: **"0 untagged posts"** with a green check. Claude's final message reads: *"Tagged 42 posts. Zero remaining untagged. Full log in ~/.wpflow/logs/wpflow.log."* |
| 1:04 – 1:15 | End card. Static for 11 seconds (this is the "pause" viewers need to read). | Three bullets:<br>**1.** `pip install wpflow`<br>**2.** Paste 3 env vars into Claude Desktop<br>**3.** Works with Hostinger / WP Engine / Kinsta / self-hosted<br>URL footer: `github.com/zedwards1226/wpflow` · `wpflow on MCPize` |

---

## Exact user message (copy/paste into Claude Desktop before recording)

```
Using wpflow: list all published posts, find any with zero tags, suggest a tag from each post's title, and update them. Show me the count before and after.
```

---

## Fallback demo (if the "100 posts with no tags" site isn't ready)

Use the same site you're running tests against. Three alternative prompts, ordered by impact:

1. **"List every inactive plugin, then show me which ones haven't had a version bump in two years."** — maps to Signal 4 ("plugin cleanup" quote), single screen, finishes in 20 seconds.
2. **"Show me all pending comments from the last 14 days and mark the ones that look like spam."** — maps to the non-coder "drowning in moderation" pain; visual because the before-state is a full pending queue, after is clean.
3. **"Find every published post tagged 'pricing' before 2026 and change the slug prefix from `/pricing-old/` to `/archive-pricing/`."** — exactly the "freelancer charges 2 hours for this" shape. Strong but less visual than the tag demo.

Use fallback #1 as the safe choice. Pick the tag-cleanup demo as hero if it records cleanly.

---

## Post-production checklist

- [ ] Cut pre-roll dead air (before 0:00).
- [ ] Cut post-roll dead air (after 1:15 end card).
- [ ] Add 1-second fade-to-black at start and end.
- [ ] Export 1080p60 H.264 MP4, ≤20 MB (Twitter native upload cap is 512 MB but small files load fast on mobile).
- [ ] Upload to Loom — get the share link.
- [ ] Upload to YouTube Unlisted — copy the `youtu.be/...` short link.
- [ ] Download the MP4 — for the Twitter/X native upload (native video outperforms link previews 3-5×).
- [ ] Grab a clean freeze-frame at 0:55 (the wp-admin "0 untagged posts" moment) — that's the MCPize hero image.

---

## What NOT to do

- No voiceover. The minute you add a voice, the file is bigger, the edit is slower, and 40% of viewers watch muted anyway.
- No intro animation. The opening card + the pre-typed prompt is the intro.
- No "smash the like button" outro. End card is 3 bullets + URL. Done.
- Don't speed up past 1.5×. Anything faster reads as a cheat and undercuts the "this is real" trust signal.
- Don't cut away from the Claude Desktop window in the middle (except the wp-admin reveal at 0:55). Every cut raises "is this a real demo?" suspicion.
