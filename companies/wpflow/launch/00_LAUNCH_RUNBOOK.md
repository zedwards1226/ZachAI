# wpflow v0.1.0 — Launch Runbook

**Target:** First 10 paying customers by 2026-04-27.
**Today:** 2026-04-21. Day 1 of the 7-day launch plan.

This file is the **order of operations**. Do steps in order. Each step has a verification ("how do I know it worked?") before moving on.

---

## Pre-Day-0 — ✅ COMPLETE (verified 2026-04-21)

Steps 1–6 done. Verified state:
- ✅ **Step 1** GitHub CLI authenticated (repo push succeeded)
- ✅ **Step 2** Public repo live: https://github.com/zedwards1226/wpflow (2 commits; README points at `pip install wpflow`)
- ✅ **Step 3** PyPI account + token (v0.1.0 successfully uploaded)
- ✅ **Step 4** PyPI upload live: https://pypi.org/project/wpflow/ returns 200, classifiers render
- ✅ **Step 5** Fresh-install smoke test passed 2026-04-21: `pip install wpflow` in clean venv installed `wpflow.exe` at `C:/Temp/wpflow-fresh/Scripts/wpflow.exe` + `import wpflow` succeeds
- ✅ **Step 6** Claude Desktop config wired with live env vars (site URL, admin user, app password, log level)

Credential-leak grep over `C:\wpflow-public` returned 0 matches for `graduatenote|Gzb5|ojiz|83KE|upfZ|bOnj|WJf4`.

---

## Pre-Day-0 reference (historical, keep for future releases)

### Step 1 — Log into GitHub CLI

```bash
gh auth login
```

- Pick: GitHub.com → HTTPS → authenticate via web browser → paste the one-time code.
- **Verify:** `gh auth status` says "Logged in to github.com account zedwards1226".

### Step 2 — Create the public repo and push

```bash
cd C:/wpflow-public
gh repo create zedwards1226/wpflow \
  --public \
  --description "WordPress operator MCP server for Claude — 25 task-scoped tools, App Password auth, local-first (stdio)." \
  --homepage "https://pypi.org/project/wpflow/" \
  --source=. \
  --remote=origin \
  --push
```

- **Verify:**
  - `gh repo view zedwards1226/wpflow --web` opens the repo in your browser.
  - README renders. LICENSE shows MIT. CI tab shows the initial workflow run (green or in-progress).
  - Grep the repo page for `graduatenote` or `Gzb5` — should be zero matches (we already scrubbed, this is the final check).

### Step 3 — Create a PyPI account + API token

1. Sign up at https://pypi.org/account/register/ with your email.
2. **Enable 2FA** — PyPI requires it for uploads.
3. After 2FA is on, go to https://pypi.org/manage/account/token/ and create a token scoped to **"Entire account"** for the first upload (you can narrow it to the `wpflow` project after the first publish).
4. Save the token (starts with `pypi-AgEI...`) somewhere you'll find it in 30 seconds.

### Step 4 — Upload the wheel and sdist to PyPI

```bash
cd C:/ZachAI/companies/wpflow
.venv/Scripts/python.exe -m twine upload dist/*
```

- When prompted for username, type: `__token__`
- When prompted for password, paste the PyPI token (including the `pypi-` prefix).
- **Verify:**
  - `pip install wpflow` in a fresh venv works.
  - https://pypi.org/project/wpflow/ renders the README + classifiers.

### Step 5 — Smoke-test a fresh install

```bash
python -m venv C:/Temp/wpflow-fresh
C:/Temp/wpflow-fresh/Scripts/python -m pip install wpflow
C:/Temp/wpflow-fresh/Scripts/wpflow --help 2>&1 | head -5
```

If the `--help` output doesn't exist (we didn't wire one), just confirm the `wpflow.exe` exists at `C:/Temp/wpflow-fresh/Scripts/wpflow.exe` and can start (it will wait on stdin — Ctrl-C to exit).

### Step 6 — Update Claude Desktop config to use the published CLI

Open `C:\Users\zedwa\AppData\Roaming\Claude\claude_desktop_config.json` and replace the existing wpflow block with:

```json
{
  "wpflow": {
    "command": "C:\\ZachAI\\companies\\wpflow\\.venv\\Scripts\\wpflow.exe",
    "env": {
      "WPFLOW_SITE_URL": "https://graduatenote.s6-tastewp.com",
      "WPFLOW_USERNAME": "admin",
      "WPFLOW_APP_PASSWORD": "<your-app-password-here>",
      "WPFLOW_LOG_LEVEL": "INFO"
    }
  }
}
```

Restart Claude Desktop. Ask Claude: *"Use wpflow to verify the connection."* You should get `{ "ok": true, "user": { "id": 1, ... } }`.

**Note:** if you'd rather Claude Desktop use the PyPI-installed version globally (so any project can use it), `pip install wpflow` into your system Python and change `"command"` to just `"wpflow"`.

---

## Day 1 (2026-04-21) — Public launch

> **Note:** originally scoped as "Day 0 = 2026-04-20." Real launch day slipped to 2026-04-21 because Steps 1-6 finished late Day 0. Day numbering below shifted by +1 day; 7-day deadline is still 2026-04-27.

### Step 7 — Record the demo video

Follow **`01_demo_video_script.md`** verbatim. Record it in Loom first (faster than YouTube). Download the MP4 too. Upload to YouTube Unlisted as a backup / embed source.

- **Verify:** 60-90 second MP4 exists at `C:/ZachAI/companies/wpflow/launch/demo.mp4`.

### Step 8 — Take the 4 screenshots for MCPize

| File | How to capture |
|---|---|
| `01-claude-desktop-with-wpflow-answering.png` | Claude Desktop on a prompt like "list pending comments". Capture the full window including the tool-call panel on the right. |
| `02-claude-desktop-config-snippet.png` | Open the JSON config, zoom to 200%, capture just the `wpflow` block. Redact the app password to `"xxxx xxxx..."` in the screenshot. |
| `03-wp-admin-application-passwords.png` | wp-admin → Profile → scroll to Application Passwords. Show the existing `wpflow` entry (redact the "last IP used" and "last used" fields if they identify you). |
| `04-tests-pass.png` | Terminal: `.venv/Scripts/python.exe test_server.py` → capture the last 30 lines showing `PASSED: 41  FAILED: 0  TOTAL: 41`. |

Drop all four into `C:/ZachAI/companies/wpflow/docs/screenshots/`, commit them to the public repo:

```bash
cp C:/ZachAI/companies/wpflow/docs/screenshots/*.png C:/wpflow-public/docs/screenshots/
cd C:/wpflow-public
git add docs/screenshots/
git commit -m "docs: add launch screenshots"
git push
```

### Step 9 — Submit the MCPize listing

1. Go to https://mcpize.com → Creator → New Listing (or whatever the current path is).
2. Copy fields from **`02_mcpize_listing.md`** into the MCPize form.
3. Configure billing tiers ($0 Free, $19 Solo, $49 Pro, $149 Agency). Enterprise = "Contact".
4. Upload the 4 screenshots + the Loom/YouTube URL.
5. Submit for review. **Expected review time:** 24-72 hours per MCPize docs.

- **Verify:** the listing shows up in your MCPize creator dashboard with status "pending review".

### Step 10 — Post to r/mcp

Open **`03_reddit_r_mcp.md`**, copy title + body into https://old.reddit.com/r/mcp/submit. Post. Pin yourself at the keyboard for the next 60 minutes and reply to every comment within 10 minutes.

- **Verify:** the post is live, you can see the permalink.

### Step 11 — Post to r/ClaudeAI (4-5 hours after Step 10)

Open **`04_reddit_r_claudeai.md`**. First-principles rewrite of the r/mcp post — do NOT crosspost. Post. Stay at the keyboard for 60 minutes.

- **Verify:** live post, replies coming in.

### End of Day 0 — metrics check

Log these numbers in a file `launch/metrics_day0.md`:

- GitHub stars: _
- PyPI downloads today: https://pypistats.org/packages/wpflow (takes a day to populate)
- r/mcp post upvotes + comments: _
- r/ClaudeAI post upvotes + comments: _
- Any install help requests? (good signal)

---

## Day 2 (2026-04-22) — Hacker News

### Step 12 — Show HN

Open **`05_hn_show_hn.md`**, post to https://news.ycombinator.com/submit. Stay at the keyboard for 60 minutes. Reply to every comment within 10 minutes.

---

## Day 3 (2026-04-23) — Reply to Messages #1-5 from MONETIZATION.md §5

5 per-person Reddit DMs / comment replies. Scripts are already in `MONETIZATION.md` §5, reply-#1 through reply-#5. Track replies in `launch/outreach.csv`.

---

## Day 4 (2026-04-24) — Reply to Messages #6-10, update posts with feedback

Same drill, messages #6-10. Go through any new issues opened in GitHub overnight — respond to every one today.

---

## Day 5 (2026-04-25) — Dev.to + Medium

Open **`06_devto_post.md`**. Post to Dev.to first. Cross-post to Medium with the canonical URL pointing back to Dev.to (for SEO). Share both links to X/Twitter.

---

## Day 6 (2026-04-26) — X / Twitter thread

Open **`07_x_thread.md`**. Schedule or post. Native MP4 upload on tweet 1. 60-minute reply window.

---

## Day 6-7 — Ship the "wow" demo (live scenario, not scripted)

Record a new Loom — 90 seconds — of Claude doing a real content-ops task on a real site. The demo video from Day 0 was scripted; this one is "first take, unedited" to build trust. Post to the r/ClaudeAI thread as a follow-up comment, cross-post to Twitter, embed in the MCPize listing.

---

## Day 7 (2026-04-27) — Collect feedback, ship v0.1.1

Scan all channels. Tag every comment / issue as bug / feature / docs / confusion. Ship a v0.1.1 with the most-requested doc clarifications (likely: clearer app-password step + a rename of `create_term` UI copy to "add category or tag").

Post a "what I learned launching wpflow" follow-up to r/ClaudeAI and r/mcp. This is free publicity, earns trust, and sets up the v0.2 expectation.

---

## What you don't do

- **Do not** boost / promote / buy ads for any post in Week 1. Organic-only.
- **Do not** crosspost verbatim between subs. Each sub gets a first-principles rewrite.
- **Do not** respond to criticism defensively. "You're right, that's a bug, opened #7" wins. "Actually the reason is…" loses.
- **Do not** ship v0.2 features during the launch week. Feedback collection only. Ship v0.2 the week after.

---

## If the metrics on 2026-04-27 (Day 7) say…

| Situation | Action |
|---|---|
| ≥3 paying subs + ≥50 installs | On track. Ship v0.2 scope, keep outreach steady. |
| 0 paying subs + ≥50 installs | Pricing / positioning is off. Drop Solo to $9/mo for 7 days as an experiment. |
| <20 installs total | Distribution is broken. Try one outreach channel not in the plan (Indie Hackers launch, Product Hunt, a WordPress subreddit allowing it). |
| <5 installs + 0 public comments | Hard kill signal. Archive the product (keep the repo public), move attention to DECISION.md #2 (Meta Ads MCP) or #5 (OpenAPI→MCP generator). |

Full kill-signal table is in `MONETIZATION.md` §7.

---

## Contacts

- **GitHub account for the push:** zedwards1226
- **PyPI account:** (create in Step 3)
- **MCPize creator account:** (create in Step 9)
- **Support email (for the README):** set up a forwarder `wpflow@<your-domain>.dev` before Step 9 — even a Cloudflare email routing rule pointed at `zedwards1226@gmail.com` is fine for launch.

Everything else you need is in the other files in this `launch/` directory.
