"""Regression test: POST endpoints require X-Internal-Secret.

Before this gate, /api/scan, /api/resolve, /api/guardrails/window-override,
and /api/agent-review were reachable by anyone on the LAN. The proxy on
:3001 injects the secret server-side so the dashboard keeps working;
direct callers without the header must get 403.
"""
import os

os.environ.setdefault("INTERNAL_API_SECRET", "test-secret-value")

from kalshi.bots.app import app
from kalshi.bots.config import INTERNAL_API_SECRET


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def test_post_without_secret_is_forbidden():
    r = _client().post("/api/scan")
    assert r.status_code == 403


def test_post_with_wrong_secret_is_forbidden():
    r = _client().post("/api/scan", headers={"X-Internal-Secret": "nope"})
    assert r.status_code == 403


def test_post_with_correct_secret_passes_gate():
    # We only care that the auth gate doesn't reject — the handler itself
    # may 500 in a test environment without a scheduler, and that's fine.
    r = _client().post("/api/scan", headers={"X-Internal-Secret": INTERNAL_API_SECRET})
    assert r.status_code != 403


def test_get_endpoints_stay_open():
    # Read endpoints must remain accessible without the header — the
    # dashboard proxy forwards GETs straight through.
    r = _client().get("/api/health")
    assert r.status_code == 200


def test_window_override_requires_secret():
    r = _client().post("/api/guardrails/window-override", json={"enabled": True})
    assert r.status_code == 403
