#!/usr/bin/env python3
"""
Claude Code PreToolUse hook.
Forwards tool-use requests to the Telegram bot approval server.
Exit 0 = allow, Exit 2 = block.
"""
import sys
import json
import urllib.request
import urllib.error

APPROVAL_URL = "http://127.0.0.1:8765/approval"
TIMEOUT_SECS = 305  # slightly over bot's 300s to avoid race


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # can't parse input — allow

    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            APPROVAL_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECS) as resp:
            result = json.loads(resp.read())

        if result.get("approved"):
            sys.exit(0)
        else:
            # Print a block message Claude Code will see
            print(json.dumps({
                "decision": "block",
                "reason": "Denied by user via Telegram",
            }))
            sys.exit(2)

    except (urllib.error.URLError, OSError):
        # Bot not running — allow by default so claude isn't stuck
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
