"""wpflow configuration loader.

Reads env vars (optionally from .env) and exposes a singleton-style Config.
No secrets are printed; callers should only log via the logging module which
passes through wp_client's secret scrubber.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


# Load .env once at import time (OK if missing).
load_dotenv(override=False)


@dataclass
class Config:
    site_url: Optional[str]
    username: Optional[str]
    app_password: Optional[str]
    allow_insecure: bool = False
    timeout_seconds: int = 30
    log_level: str = "INFO"
    max_upload_mb: int = 25
    upload_roots: List[Path] = field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return bool(self.site_url and self.username and self.app_password)

    @property
    def missing_vars(self) -> List[str]:
        missing = []
        if not self.site_url:
            missing.append("WPFLOW_SITE_URL")
        if not self.username:
            missing.append("WPFLOW_USERNAME")
        if not self.app_password:
            missing.append("WPFLOW_APP_PASSWORD")
        return missing

    @property
    def normalized_app_password(self) -> str:
        """Strip outer whitespace, preserve interior spaces (they are part of the credential)."""
        return (self.app_password or "").strip()

    @property
    def base_url(self) -> str:
        return (self.site_url or "").rstrip("/")


def _default_upload_roots() -> List[Path]:
    home = Path.home()
    roots = []
    for name in ("Downloads", "Pictures"):
        p = home / name
        if p.exists():
            roots.append(p)
    return roots


def load_config() -> Config:
    site = os.environ.get("WPFLOW_SITE_URL") or os.environ.get("WPFLOW_TEST_SITE_URL")
    user = os.environ.get("WPFLOW_USERNAME") or os.environ.get("WPFLOW_TEST_USERNAME")
    pw = os.environ.get("WPFLOW_APP_PASSWORD") or os.environ.get("WPFLOW_TEST_APP_PASSWORD")

    allow_insecure = os.environ.get("WPFLOW_ALLOW_INSECURE", "0") in ("1", "true", "True", "yes")
    try:
        timeout = int(os.environ.get("WPFLOW_TIMEOUT_SECONDS", "30"))
    except ValueError:
        timeout = 30
    log_level = os.environ.get("WPFLOW_LOG_LEVEL", "INFO").upper()
    try:
        max_upload_mb = int(os.environ.get("WPFLOW_MAX_UPLOAD_MB", "25"))
    except ValueError:
        max_upload_mb = 25

    roots_env = os.environ.get("WPFLOW_UPLOAD_ROOT", "")
    if roots_env:
        upload_roots = [Path(p.strip()).resolve() for p in roots_env.split(",") if p.strip()]
    else:
        upload_roots = [p.resolve() for p in _default_upload_roots()]

    return Config(
        site_url=site,
        username=user,
        app_password=pw,
        allow_insecure=allow_insecure,
        timeout_seconds=timeout,
        log_level=log_level,
        max_upload_mb=max_upload_mb,
        upload_roots=upload_roots,
    )


CONFIG = load_config()
