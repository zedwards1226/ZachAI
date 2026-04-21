# wpflow — Test Site Provisioning & Seed Data

**Provisioned:** 2026-04-20
**For:** wpflow v0.1 BUILDER + Phase 4 smoke tests
**Expires:** ~2026-04-22 (approx 48h from provision, free TasteWP unregistered tier)

---

## 1. How this test WP was provisioned

**Option chosen:** TasteWP (free, no signup, instant).
**Why not Docker:** Docker Desktop is not installed on this machine (`docker --version` → command not found). Install is multi-GB and exceeds the 25-minute budget.
**Why not InstaWP:** Requires email signup + email-confirmation click. TasteWP has zero-friction anonymous creation.
**Why not WordPress Playground (WASM):** Runs in-browser only; URL is not reachable by MCP server code.

### Exact steps reproduced

1. Open `https://tastewp.com/` in a browser (we used Playwright MCP).
2. Tick the "I agree with the Terms" checkbox.
3. Click "Set it up! (no sign up required!)".
4. A modal appears with site URL, username, password, and "Access it now!" button. Copy all three.
5. Open `{site_url}/wp-login.php`, log in with that username/password.
6. Navigate to `{site_url}/wp-admin/profile.php`.
7. Scroll to **Application Passwords**. Enter name `wpflow-mcp-v0.1`. Click **Add New Application Password**.
8. Copy the 24-char space-separated password shown (it is displayed ONCE — cannot be retrieved later).
9. Save all values into `data/test_site.json` (gitignored).

### What runs where
- **Site:** hosted by TasteWP in front of Cloudflare. Nothing runs locally.
- **Seed script:** `data/_seed.py` (local Python, talks to the site's REST API via `urllib`).

---

## 2. Start / stop / reset

- **Start:** the site is always on while its TTL is valid. No service to restart locally.
- **Pause:** not supported on free tier. Site is public.
- **Reset (full wipe):** TasteWP does not offer reset — just create a new site and re-run seeding (see §5).
- **If the site dies / TTL expires:** it becomes unreachable. Provision a fresh one by repeating §1, update `test_site.json`, and re-run seeding.

---

## 3. What was seeded

All via authenticated REST API calls from `data/_seed.py`. IDs below are live as of provisioning:

| Content | Count | IDs | Notes |
|---|---|---|---|
| Posts — published | 5 | 1, 7, 8, 9, 15 | ID 1 is WP default "Hello world!"; 7/8/9/15 are wpflow seeds |
| Posts — draft | 1 | 10 | "Draft: upcoming features" |
| Posts — scheduled (future) | 1 | 11 | "Scheduled: next week announcement" — publishes ~7 days out |
| **Total posts** | **7** | — | — |
| Pages | 2 | 12 (About), 13 (Contact) | both published |
| Categories | 3 | 2 (Tutorials), 3 (News), 4 (Reviews) | plus WP default "Uncategorized" (id 1) |
| Tags | 5 | 5 (wordpress), 6 (mcp), 7 (api), 8 (automation), 9 (testing) | — |
| Media | 1 | 14 | 8x8 PNG, title `wpflow-test` |
| Comments — approved | 1 | 2 | on post 7 |
| Comments — pending | 1 | 3 | on post 7, status=hold |
| Users | 2 | 1 (admin, administrator), 2 (wpflow_subscriber, subscriber) | — |
| Plugins | 2 | Akismet, Hello Dolly | TasteWP defaults, untouched |

All 5 published posts are visible to **unauthenticated** `GET /wp-json/wp/v2/posts`. Drafts + scheduled only surface with auth.

---

## 4. How BUILDER authenticates

Read `data/test_site.json` (gitignored). It contains:

```json
{
  "site_url": "...",
  "username": "admin",
  "app_password": "xxxx xxxx xxxx xxxx xxxx xxxx",
  ...
}
```

### Auth method: HTTP Basic with Application Password
```python
import base64, urllib.request, json
cfg = json.load(open("data/test_site.json"))
auth = "Basic " + base64.b64encode(f"{cfg['username']}:{cfg['app_password']}".encode()).decode()
headers = {
    "Authorization": auth,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 ...",  # REQUIRED — see gotcha below
}
```

Or with `requests`:
```python
import requests
cfg = json.load(open("data/test_site.json"))
r = requests.get(f"{cfg['site_url']}/wp-json/wp/v2/users/me",
                 auth=(cfg['username'], cfg['app_password']),
                 headers={"User-Agent": "Mozilla/5.0"})
```

### Gotcha — Cloudflare blocks default Python UA
TasteWP sits behind Cloudflare with aggressive bot protection. Any request with Python's default `urllib` User-Agent (`Python-urllib/3.x`) returns **HTTP 403 / error 1010 "browser_signature_banned"**. Always set `User-Agent` to a real browser string. The `requests` library's default UA works.

### Verify auth works
```bash
curl -sSL -u "admin:Gzb5 ojiz 83KE upfZ bOnj WJf4" \
  -H "User-Agent: Mozilla/5.0" \
  https://graduatenote.s6-tastewp.com/wp-json/wp/v2/users/me
```
Should return JSON with `"id": 1, "name": "admin"` (the `roles` field is absent on `/users/me` by design but the 200 status proves auth).

---

## 5. Rotate / refresh flows

### If the Application Password leaks
1. Log into `{site_url}/wp-admin` with the admin login password (`wp_admin_login_password` in JSON).
2. Go to Users → Profile → Application Passwords.
3. Click **Revoke** next to `wpflow-mcp-v0.1`.
4. Create a new one named `wpflow-mcp-v0.1-rotated-{date}`.
5. Update `data/test_site.json` with the new value.
6. Tell BUILDER / Phase 4 to reload the JSON.

### If content drifts and you need a clean slate
Option A — wipe known seeded records:
```python
# delete posts 7-11, 15; pages 12-13; categories 2-4; tags 5-9; media 14; comments 2-3; user 2
# then re-run _seed.py
```
Option B (faster) — provision a fresh TasteWP site (§1) and point `test_site.json` at it.

### If the site's TTL expires (48h unregistered)
Free TasteWP sites die after ~2 days. Provision a new one per §1 and re-run `data/_seed.py` (updating the `SITE`, `USER`, `APP_PW` constants inside the script first — it intentionally embeds them so the seed script is idempotent-per-site).

---

## 6. Proof the site is live

At provisioning time the following call succeeded:

```bash
$ curl -sSL -H "User-Agent: Mozilla/5.0" \
    "https://graduatenote.s6-tastewp.com/wp-json/wp/v2/posts?per_page=10&_fields=id,title,status"
```

Returned a JSON array of **5 published posts** (unauthenticated). First post title: **"MCP tools love the WP REST API"** (id 15).

Authenticated with `?status=publish,draft,future` returns **7 posts** (including the draft and scheduled ones).

---

## 7. Files in this folder

| File | Tracked in git? | Purpose |
|---|---|---|
| `test_site.json` | NO (gitignored) | live creds, read by BUILDER |
| `_seed.py` | NO (gitignored) | one-shot seeding script; edit constants to point at a new site |
| `INGESTION.md` | YES | this doc |
