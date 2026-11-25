"""Input sanitization and reserved parameter collision protection."""

from typing import Any

from medicare.config import settings
from medicare.domain.errors import ModelNotAllowedError, ReservedParameterError

RESERVED_KEYS = frozenset({"thread_id", "user_id", "model", "checkpoint_id", "checkpoint_ns"})


def validate_agent_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Verify that custom agent_config contains no reserved internal keys.

    Raises:
        ReservedParameterError: If any reserved key is found in config.
    """
    if not config:
        return {}

    for key in config:
        if key in RESERVED_KEYS:
            raise ReservedParameterError(key)

    return config


def validate_requested_model(requested_model: str | None) -> str:
    """Verify that requested model is present in the active system allowlist.

    Raises:
        ModelNotAllowedError: If the model is not in ALLOWED_MODELS.
    """
    if not requested_model:
        return settings.DEFAULT_MODEL

    if requested_model not in settings.ALLOWED_MODELS:
        raise ModelNotAllowedError(requested_model)

    return requested_model
