"""Runtime configuration. Reads .env, allows overrides from the Setup page."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# On Azure App Service only /home survives a restart, so CI_DATA_DIR=/home/data there.
DATA_DIR = Path(os.getenv("CI_DATA_DIR") or ROOT / "data")
UPLOAD_DIR = DATA_DIR / "uploads"
THUMB_DIR = DATA_DIR / "thumbs"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "intel.sqlite"

for _d in (DATA_DIR, UPLOAD_DIR, THUMB_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

PROVIDERS = ("mock", "openai", "azure", "gemini")


def secret(name: str, default: str = "") -> str:
    """Read config from Streamlit Cloud secrets first, then the environment.

    Streamlit Cloud injects values into st.secrets; whether they also reach
    os.environ has varied between versions, so check both rather than assume.
    """
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - streamlit absent, no secrets file, or bare mode
        pass
    return os.getenv(name, default)


@dataclass
class Settings:
    provider: str = field(default_factory=lambda: secret("CI_PROVIDER", "mock"))
    api_key: str = field(
        default_factory=lambda: secret("OPENAI_API_KEY")
        or secret("AZURE_OPENAI_API_KEY")
        or secret("GEMINI_API_KEY")
        or ""
    )
    endpoint: str = field(default_factory=lambda: secret("AZURE_OPENAI_ENDPOINT"))
    api_version: str = field(
        default_factory=lambda: secret("AZURE_OPENAI_API_VERSION", "2024-10-21")
    )
    text_model: str = field(default_factory=lambda: secret("CI_TEXT_MODEL", "gpt-4o-mini"))
    vision_model: str = field(default_factory=lambda: secret("CI_VISION_MODEL", "gpt-4o-mini"))
    # Serve pre-processed results instead of calling the API. Demo-day safety net.
    demo_mode: bool = field(default_factory=lambda: secret("CI_DEMO_MODE", "0") == "1")
    # Gate the UI when the app is reachable from outside the machine. Empty = no gate.
    app_password: str = field(default_factory=lambda: secret("CI_APP_PASSWORD", ""))

    @property
    def is_live(self) -> bool:
        return self.provider != "mock" and bool(self.api_key)


_settings = Settings()

# Environment variables do not cross terminals, so record whether the access gate
# is on. tunnel.ps1 runs in a separate shell and needs to know the app's real state.
GATE_MARKER = DATA_DIR / ".gate"
try:
    GATE_MARKER.write_text("1" if _settings.app_password else "0", encoding="utf-8")
except OSError:
    pass


def get_settings() -> Settings:
    return _settings


def update_settings(**kwargs) -> Settings:
    for key, value in kwargs.items():
        if hasattr(_settings, key):
            setattr(_settings, key, value)
    return _settings
