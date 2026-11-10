"""Loads config.yaml (Telegram ids etc.) overlaid with the app-editable settings.

docs/data/settings.json holds the settings you can change from the web app
(watchlist, pre-filter keywords, director-buy threshold). Anything present
there wins over the same key in config.yaml, so the app can edit them without
touching the YAML. If the JSON is missing or invalid, config.yaml is used as-is.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _REPO_ROOT / "config.yaml"
SETTINGS_PATH = _REPO_ROOT / "docs" / "data" / "settings.json"

APP_EDITABLE_KEYS = ("watchlist", "keywords", "min_director_buy_value")


def load_config(path: Path = DEFAULT_CONFIG_PATH, settings_path: Path = SETTINGS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config

    if isinstance(settings, dict):
        for key in APP_EDITABLE_KEYS:
            if key in settings and settings[key] is not None:
                config[key] = settings[key]
    return config
