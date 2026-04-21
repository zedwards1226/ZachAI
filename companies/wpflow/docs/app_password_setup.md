# How to create a WordPress Application Password for wpflow

**You'll need:** admin (or editor) access to your WordPress site, a browser, and 60 seconds.

This is the only auth step. wpflow uses nothing else — no OAuth, no plugin install on the WP side, no vendor app review.

---

## Step 1 — Open your WordPress profile

Log into your WordPress admin at `https://<your-site>/wp-admin`, click your username in the top-right corner, then click **Edit Profile**.

> Direct URL: `https://<your-site>/wp-admin/profile.php`

## Step 2 — Scroll to "Application Passwords"

Scroll to the bottom of the profile page. You should see a section titled **Application Passwords** (WordPress 5.6+).

**Don't see it?**
- Make sure you're on WordPress 5.6 or newer.
- On some hosts (managed WP shared plans) it's hidden behind a feature flag — search the plugin list for "Application Passwords" and activate.
- Some security plugins (iThemes Security, Wordfence with strict settings) disable the feature. Temporarily allow it, or add its endpoint (`/wp-json/wp/v2/users/*/application-passwords`) to the allowlist.

## Step 3 — Generate a password named `wpflow`

In the "New Application Password Name" box, type:

```
wpflow
```

Click **Add New Application Password**.

WordPress will show a one-time screen displaying a 24-character password split into six groups of 4, like:

```
abcd efgh ijkl mnop qrst uvwx
```

**Copy it exactly as shown.** The spaces are part of the credential — don't strip them, don't remove them. This password will never be shown again.

## Step 4 — Paste into your Claude Desktop config

Open your Claude Desktop config at:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

Add (or update) the `wpflow` entry:

```json
{
  "mcpServers": {
    "wpflow": {
      "command": "wpflow",
      "env": {
        "WPFLOW_SITE_URL": "https://your-site.com",
        "WPFLOW_USERNAME": "your-wp-username",
        "WPFLOW_APP_PASSWORD": "abcd efgh ijkl mnop qrst uvwx"
      }
    }
  }
}
```

Restart Claude Desktop. Ask Claude:

> "Use wpflow to verify the connection."

You should see `{ "ok": true, "user": { ... }, "site_url": "..." }`.

## If you get stuck

| Error | Fix |
|---|---|
| `auth_failed` | The app password is 24 chars with spaces. Copy it exactly — don't strip the spaces. |
| `rest_api_disabled` | A security plugin or `.htaccess` rule turned off the WP REST API. Re-enable at Settings → Permalinks (just click Save). |
| `rest_disabled_for_plugins` | Some hosts block `/wp-json/wp/v2/plugins` specifically. Manage plugins in wp-admin, or migrate to a host that exposes the full REST surface. |
| Cloudflare 403 / error 1010 | You're behind Cloudflare Bot Management. wpflow sends a browser-like User-Agent, so this shouldn't happen out of the box. If it does, your host has additional rules — contact them to allowlist your machine's IP, or test from a different network. |

## To revoke

Open `/wp-admin/profile.php` again, find the "wpflow" row under Application Passwords, click **Revoke**. That immediately invalidates the credential. No need to restart wpflow — the next call just fails with `auth_failed`.

## Per-site, not per-user

If you add wpflow to a second WordPress site, generate a separate application password on that site. They're not transferable.

---

## Screenshots

- `screenshots/01-profile-edit.png` — Where to find the Edit Profile link.
- `screenshots/02-application-passwords-panel.png` — The Application Passwords section on the profile page.
- `screenshots/03-generated-password.png` — What the 24-char password looks like when WordPress shows it to you.

*(Drop the three screenshots into `docs/screenshots/` before the launch post goes up. See `../LAUNCH_RUNBOOK.md` for the shot list.)*
