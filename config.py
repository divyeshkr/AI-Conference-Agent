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

PROVIDERS = ("mock", "openai", "azure", "gemini", "groq")

# Providers that speak the OpenAI wire format differ only by base URL and model
# names, so they need no separate client code.
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "",
        "text_model": "gpt-4o-mini",
        "vision_model": "gpt-4o-mini",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "text_model": "llama-3.3-70b-versatile",
        "vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
    },
    "gemini": {
        "base_url": "",
        "text_model": "gemini-flash-latest",
        "vision_model": "gemini-flash-latest",
    },
    "azure": {
        "base_url": "",
        "text_model": "gpt-4o-mini",
        "vision_model": "gpt-4o-mini",
    },
}


def provider_default(provider: str, key: str) -> str:
    return PROVIDER_DEFAULTS.get(provider, {}).get(key, "")


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
        default_factory=lambda: secret("GROQ_API_KEY")
        or secret("OPENAI_API_KEY")
        or secret("AZURE_OPENAI_API_KEY")
        or secret("GEMINI_API_KEY")
        or ""
    )
    endpoint: str = field(default_factory=lambda: secret("AZURE_OPENAI_ENDPOINT"))
    # Any OpenAI-compatible host. Blank means the provider's own default.
    base_url: str = field(default_factory=lambda: secret("CI_BASE_URL"))
    api_version: str = field(
        default_factory=lambda: secret("AZURE_OPENAI_API_VERSION", "2024-10-21")
    )
    text_model: str = field(default_factory=lambda: secret("CI_TEXT_MODEL"))
    vision_model: str = field(default_factory=lambda: secret("CI_VISION_MODEL"))
    # Serve pre-processed results instead of calling the API. Demo-day safety net.
    demo_mode: bool = field(default_factory=lambda: secret("CI_DEMO_MODE", "0") == "1")
    # Gate the UI when the app is reachable from outside the machine. Empty = no gate.
    app_password: str = field(default_factory=lambda: secret("CI_APP_PASSWORD", ""))
    # Set when CI_PROVIDER held a value this build does not recognise.
    invalid_provider: str = ""

    def __post_init__(self) -> None:
        # A bad CI_PROVIDER value must degrade to mock, never crash the UI.
        if self.provider not in PROVIDERS:
            self.invalid_provider = self.provider
            self.provider = "mock"
        self.apply_provider_defaults()

    def apply_provider_defaults(self) -> None:
        """Fill blank model/base_url fields from the provider's defaults."""
        for key in ("base_url", "text_model", "vision_model"):
            if not getattr(self, key):
                setattr(self, key, provider_default(self.provider, key))

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
