"""Centralized configuration loader for application identity, messages, verifier terms, and prompts."""

import functools
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _get_config_dir() -> Path:
    """Find config/ directory relative to settings or repo root."""
    try:
        from medicare.config import settings

        cdir = Path(getattr(settings, "CONFIG_DIR", "config"))
        if cdir.exists():
            return cdir
    except Exception:
        pass
    return _REPO_ROOT / "config"


@functools.lru_cache(maxsize=1)
def get_app_config() -> dict[str, Any]:
    """Load config/app.yaml with caching."""
    cfg_path = _get_config_dir() / "app.yaml"
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Failed to load app.yaml (%s)", e)
    return {}


@functools.lru_cache(maxsize=1)
def get_messages() -> dict[str, str]:
    """Load config/messages.yaml with caching."""
    msg_path = _get_config_dir() / "messages.yaml"
    if msg_path.exists():
        try:
            with open(msg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Failed to load messages.yaml (%s)", e)
    return {}


@functools.lru_cache(maxsize=1)
def get_verifier_terms() -> dict[str, Any]:
    """Load config/verifier_terms.yaml with caching."""
    terms_path = _get_config_dir() / "verifier_terms.yaml"
    if terms_path.exists():
        try:
            with open(terms_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Failed to load verifier_terms.yaml (%s)", e)
    return {}


@functools.lru_cache(maxsize=1)
def get_intent_words() -> dict[str, Any]:
    """Load config/intent_words.yaml with caching."""
    iw_path = _get_config_dir() / "intent_words.yaml"
    if iw_path.exists():
        try:
            with open(iw_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Failed to load intent_words.yaml (%s)", e)
    return {}


def clear_config_cache() -> None:
    """Clear cached configuration dictionaries (useful in tests when files change)."""
    get_app_config.cache_clear()
    get_messages.cache_clear()
    get_verifier_terms.cache_clear()
    get_intent_words.cache_clear()
    _read_prompt_template.cache_clear()


def msg(key: str, **kwargs: Any) -> str:
    """Retrieve and format a user-facing message string from config/messages.yaml."""
    messages = get_messages()
    app_cfg = get_app_config()

    template = messages.get(key)
    if template is None:
        ui_cfg = app_cfg.get("ui", {})
        template = str(ui_cfg[key]) if key in ui_cfg else key

    params: dict[str, Any] = {
        "app_name": app_cfg.get("app_name", ""),
        "currency_symbol": app_cfg.get("currency_symbol", ""),
        "currency_code": app_cfg.get("currency_code", ""),
        "disclaimer": app_cfg.get("ui", {}).get("disclaimer_footer", ""),
    }
    try:
        from medicare.config import settings

        params["emergency_helpline"] = getattr(settings, "HELPLINE_EMERGENCY", "")
        params["crisis_helpline"] = getattr(settings, "HELPLINE_MENTAL_HEALTH", "")
    except Exception:
        params["emergency_helpline"] = ""
        params["crisis_helpline"] = ""

    params.update(kwargs)

    try:
        return template.format(**params)
    except KeyError:
        return template


@functools.lru_cache(maxsize=32)
def _read_prompt_template(name: str) -> str:
    """Read prompt markdown file from config/prompts/<name>.md."""
    prompts_dir = _get_config_dir() / "prompts"
    clean_name = name[:-3] if name.endswith(".md") else name
    p = prompts_dir / f"{clean_name}.md"
    if not p.exists():
        raise FileNotFoundError(f"Prompt template file not found: {p}")
    return p.read_text(encoding="utf-8")


def get_prompt(name: str, **kwargs: Any) -> str:
    """Retrieve and format a prompt template from config/prompts/<name>.md."""
    raw_template = _read_prompt_template(name)
    app_cfg = get_app_config()

    defaults = {
        "app_name": app_cfg.get("app_name", ""),
        "domain_description": app_cfg.get("domain_description", ""),
        "currency_symbol": app_cfg.get("currency_symbol", ""),
        "currency_code": app_cfg.get("currency_code", ""),
        "disclaimer": app_cfg.get("ui", {}).get("disclaimer_footer", ""),
    }
    defaults.update(kwargs)

    formatted = raw_template
    for k, v in defaults.items():
        formatted = formatted.replace(f"{{{k}}}", str(v))

    return formatted


def validate_prompts_at_startup() -> None:
    """Validate all prompt template files exist and are loadable."""
    prompts_dir = _get_config_dir() / "prompts"
    if not prompts_dir.exists():
        raise FileNotFoundError(f"Prompts directory missing: {prompts_dir}")

    required_prompts = [
        "router",
        "conversational",
        "sql_generator",
        "sql_fixer",
        "synthesizer",
        "supervisor",
        "chunk_grader",
        "query_rewrite",
        "verifier_repair",
        "schema_retry",
    ]
    missing = []
    for rp in required_prompts:
        pfile = prompts_dir / f"{rp}.md"
        if not pfile.exists():
            missing.append(rp)

    if missing:
        raise RuntimeError(f"Missing prompt files: {missing}")
