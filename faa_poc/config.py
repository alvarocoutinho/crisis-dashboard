"""Colab-friendly configuration for the frozen proof of concept."""
from __future__ import annotations
import os
from typing import Any

CONFIG: dict[str, Any] = {
    # Execution
    "MODE": "FULL_PIPELINE",  # FULL_PIPELINE | CEMADEN_ONLY | CEMADEN_PED_ONLY | YOUTUBE_ONLY | COMMENT_REFRESH_ONLY
    "OUTPUT_DIR": "./outputs",
    "INTERACTIVE_CREDENTIALS": True,

    # Scope — frozen for the proof of concept
    "FILTER_UF": None,
    "FILTER_LEVELS": ["moderado", "alto", "muito alto"],
    "FILTER_EVENTS": ["Movimentos de Massa", "Risco Hidrológico"],
    "MAX_ALERTS": None,

    # Credentials — prefer environment variables / Colab Secrets
    "PED_EMAIL": "",
    "PED_PASSWORD": "",
    "YOUTUBE_API_KEY": "",

    # Alert-anchored YouTube retrieval window
    "SEARCH_PRE_ALERT_HOURS": 6,
    "SEARCH_POST_ALERT_HOURS": 72,
    "EVENT_WINDOW_HOURS": 72,
    "MAX_VIDEOS_PER_ALERT": 5,
    "MAX_COMMENT_PAGES": 5,
    "YT_COMMENT_ORDER": "time",

    # Quota management
    "YT_QUOTA_CEILING": 2400,
    "YT_QUOTA_HIGH_RESERVE": 400,

    # Relevance rules
    "MIN_GEO_SCORE": 2.0,
    "MIN_EVENT_SCORE": 1.5,
    "MIN_RELEVANCE_SCORE": 5.0,
    "ALLOW_STATE_LEVEL_MATCHES": True,

    # PED
    "PED_REFRESH_COOLDOWN_SECONDS": 900,

    # Lifecycle
    "ALERT_TRACKING_DAYS": 7,
    "FORCE_REPROCESS": False,
}

_ENV_KEYS = ("PED_EMAIL", "PED_PASSWORD", "YOUTUBE_API_KEY", "OUTPUT_DIR")

def build_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(CONFIG)
    for key in _ENV_KEYS:
        value = os.environ.get(key)
        if value:
            cfg[key] = value
    if overrides:
        cfg.update(overrides)
    return cfg
