"""UI-layer configuration loader independent of backend medicare package."""

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent


_CONFIG_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def get_app_config() -> dict[str, Any]:
    """Load config/app.yaml directly from filesystem, refreshing automatically on file change."""
    cfg_path = _REPO_ROOT / "config" / "app.yaml"
    if cfg_path.exists():
        try:
            mtime = cfg_path.stat().st_mtime
            if "app" in _CONFIG_CACHE and _CONFIG_CACHE["app"][0] == mtime:
                return _CONFIG_CACHE["app"][1]
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    _CONFIG_CACHE["app"] = (mtime, data)
                    return data
        except Exception:
            pass
    return {}


def get_messages_config() -> dict[str, Any]:
    """Load config/messages.yaml directly from filesystem, refreshing automatically on file change."""
    cfg_path = _REPO_ROOT / "config" / "messages.yaml"
    if cfg_path.exists():
        try:
            mtime = cfg_path.stat().st_mtime
            if "messages" in _CONFIG_CACHE and _CONFIG_CACHE["messages"][0] == mtime:
                return _CONFIG_CACHE["messages"][1]
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    _CONFIG_CACHE["messages"] = (mtime, data)
                    return data
        except Exception:
            pass
    return {}
