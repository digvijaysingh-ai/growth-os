"""Loads config.toml and .env. Secrets come only from the environment."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines, existing environment wins."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Secrets:
    meta_token: str
    meta_account: str
    meta_version: str
    site_url: str
    site_token: str

    @classmethod
    def from_env(cls) -> "Secrets":
        account = os.environ.get("META_AD_ACCOUNT_ID", "")
        if account and not account.startswith("act_"):
            account = "act_" + account
        return cls(
            meta_token=os.environ.get("META_ACCESS_TOKEN", ""),
            meta_account=account,
            meta_version=os.environ.get("META_API_VERSION", "v23.0"),
            site_url=os.environ.get("SITE_AGENT_URL", ""),
            site_token=os.environ.get("SITE_AGENT_TOKEN", ""),
        )

    def missing(self) -> list[str]:
        names = {"META_ACCESS_TOKEN": self.meta_token, "META_AD_ACCOUNT_ID": self.meta_account,
                 "SITE_AGENT_URL": self.site_url, "SITE_AGENT_TOKEN": self.site_token}
        return [k for k, v in names.items() if not v]


def load_config(path: Path | None = None) -> dict:
    path = path or (ROOT / "config.toml" if (ROOT / "config.toml").is_file() else ROOT / "config.example.toml")
    with path.open("rb") as f:
        return tomllib.load(f)
