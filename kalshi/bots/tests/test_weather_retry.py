"""Tests for weather.py retry wrapper — a single Open-Meteo flake must not
kill the whole 15-min scan cycle."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import weather


class FakeResp:
    def __init__(self, data=None, status=200):
        self._data = data or {}
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")
    def json(self):
        return self._data


def test_retry_succeeds_on_first_try(monkeypatch):
    calls = []
    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return FakeResp({"ok": True})
    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)

    resp = weather._get_with_retry("http://x", {}, attempts=3)
    assert resp.json() == {"ok": True}
    assert len(calls) == 1


def test_retry_succeeds_after_two_failures(monkeypatch):
    n = {"count": 0}
    def fake_get(url, params=None, timeout=None):
        n["count"] += 1
        if n["count"] < 3:
            raise ConnectionError("flake")
        return FakeResp({"ok": True})
    monkeypatch.setattr(weather.requests, "get", fake_get)
    sleeps = []
    monkeypatch.setattr(weather.time, "sleep", lambda s: sleeps.append(s))

    resp = weather._get_with_retry("http://x", {}, attempts=3)
    assert resp.json() == {"ok": True}
    assert n["count"] == 3
    assert sleeps == [1, 2]  # backoff 1s, 2s before 3rd attempt


def test_retry_raises_after_all_attempts_fail(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise ConnectionError("down")
    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)

    with pytest.raises(ConnectionError):
        weather._get_with_retry("http://x", {}, attempts=3)


def test_retry_propagates_http_error(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return FakeResp(status=503)
    monkeypatch.setattr(weather.requests, "get", fake_get)
    monkeypatch.setattr(weather.time, "sleep", lambda s: None)

    import requests
    with pytest.raises(requests.HTTPError):
        weather._get_with_retry("http://x", {}, attempts=3)
