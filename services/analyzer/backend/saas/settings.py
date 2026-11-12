from shared.paths import PROJECT_ROOT
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = PROJECT_ROOT


@dataclass(frozen=True)
class Settings:
    data: Path
    origin: str = "http://127.0.0.1:8770"
    development: bool = False
    max_pending: int = 8
    daily_jobs: int = 100
    session_seconds: int = 8 * 3600
    allow_eda: bool = False
    auth_enabled: bool = True

    def __post_init__(self):
        u = urlsplit(self.origin)
        if u.scheme not in {"http", "https"} or not u.hostname or u.path or u.query or u.fragment or u.username:
            raise ValueError("EV_SAAS_ORIGIN must be an origin without path or credentials")
        if u.scheme != "https" and not (self.development and u.hostname in {"localhost", "127.0.0.1"}):
            raise ValueError("HTTPS is required; HTTP development is loopback-only")
        if not self.auth_enabled and not (self.development and u.hostname in {"localhost", "127.0.0.1"}):
            raise ValueError("Login-free preview is only available in loopback development mode")
        if self.data.resolve() == (ROOT / ".runtime").resolve():
            raise ValueError("Use a separate SaaS data directory; local projects are not migrated automatically")

    @property
    def secure(self):
        return self.origin.startswith("https://")

    @property
    def cookie(self):
        return "__Host-ev_session" if self.secure else "ev_session"

    @classmethod
    def from_env(cls):
        origin = os.getenv("EV_SAAS_ORIGIN", "http://127.0.0.1:8770")
        development = os.getenv("EV_SAAS_DEVELOPMENT") == "1"
        preview = development and urlsplit(origin).hostname in {"localhost", "127.0.0.1"}
        return cls(
            data=Path(os.getenv("EV_SAAS_DATA", str(ROOT / ".runtime/saas"))),
            origin=origin,
            development=development,
            max_pending=int(os.getenv("EV_SAAS_MAX_PENDING", "8")),
            daily_jobs=int(os.getenv("EV_SAAS_DAILY_JOBS", "100")),
            allow_eda=os.getenv("EV_SAAS_ISOLATED_EDA") == "1",
            auth_enabled=os.getenv("EV_SAAS_AUTH_ENABLED", "0" if preview else "1") != "0",
        )
