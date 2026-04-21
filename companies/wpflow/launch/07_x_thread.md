# X / Twitter — Day 5 launch thread

**Account:** Zach's X account.
**When:** Day 5. By now Reddit + HN have created first-wave awareness; X thread amplifies to a different crowd (solopreneurs, WP buyers, non-coders).
**Best time:** Tue-Thu, 10 AM or 3 PM ET.
**Format:** 8 tweets. First is the hook (with the DEMAND_SIGNALS Signal 4 quote), middle 6 are one-tool-one-example, last is the CTA.
**Media:** attach the demo MP4 **natively** to tweet 1 (not a link). Native video ranks 3-5× higher. Make sure the MP4 autoplays and makes sense muted.

---

## Tweet 1 — Hook (280 char budget)

```
"I own a WordPress site. A past developer left the codebase in rough shape… I am not a developer and I don't code."

Claude can now run your WordPress site end-to-end. No OAuth. No plugin to install on the WP side. 3-line config. pip install wpflow.

Thread ↓
```

**Attach:** the 75-second demo MP4.

---

## Tweet 2 — Posts (one tool, one real prompt)

```
1 / wpflow ships 25 tools. First 6 are for posts.

Prompt: "List every post tagged 'pricing' before 2026, update the slug from /pricing-old/ to /archive-pricing/."

One Claude message → list_posts + update_post in a loop → done. About 2 hours of freelancer work.
```

---

## Tweet 3 — Plugins

```
2 / "My site has 40 plugins. Show me which are inactive and haven't been updated in 2 years so I can delete them."

list_plugins returns compact summaries. Claude reads them, picks the stale ones, deactivates by slug. You click delete.

This is the "past dev left a mess" cleanup loop.
```

---

## Tweet 4 — Comments

```
3 / "Moderate the pending comments queue. Approve anything from a real human, spam obvious promo."

list_comments + moderate_comment. Claude reads context, marks each. The thing every WP owner puts off for 6 months — now it's a one-prompt job.
```

---

## Tweet 5 — Media

```
4 / "Upload this folder of 12 screenshots to the Media Library and name them after their filenames."

upload_media with MIME whitelist (jpeg/png/gif/webp/svg/mp4/pdf), SSRF guard, 25 MB cap.

Your agent can't accidentally upload the wrong thing or pull from your private network.
```

---

## Tweet 6 — Taxonomy

```
5 / "Add a 'Case Studies' category and tag every post that mentions our enterprise customers with it."

create_term + list_posts(search=...) + update_post. The kind of content-ops work that dies in your backlog forever. Gone in 3 minutes.
```

---

## Tweet 7 — Health

```
6 / "Run a site health check. Tell me if anything's critical."

site_health reads WordPress's own Site Health module. Claude reads the JSON, summarizes in English, highlights actionable issues.

Your WP support ticket before you open it.
```

---

## Tweet 8 — CTA (280 char budget)

```
7 / Install: pip install wpflow

3 env vars in your Claude Desktop config. 60 seconds.

MIT licensed, source public. Free tier = 1 site, self-host. Paid tiers for multi-site + support on MCPize.

GitHub: github.com/zedwards1226/wpflow
```

---

## After the thread

- Pin the thread to your profile for 48 hours.
- Quote-tweet the hook with "today's launch" 24 hours later (different angle, same thread).
- Reply to every comment within 30 minutes for the first 2 hours.
- DO NOT buy reach, boost, or "X blue ad" this thread. Organic-only on launch — paid amplification at v0.1 with zero real subs converts badly and taints your follower signal for the rest of the year.

## Second thread (Day 12, once some users exist)

Repeat the same shape but with **one real user's before/after** in the hook tweet. Ask the user for permission. One concrete case replaces all 6 of the "imagine if" middle tweets and converts dramatically better.
