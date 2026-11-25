"""Domain-specific typed errors for MediCare."""


class MediCareError(Exception):
    """Base class for all MediCare domain exceptions."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthenticationRequiredError(MediCareError):
    """Raised when Bearer authorization is missing or invalid."""

    def __init__(self, message: str = "Invalid or missing Bearer credentials") -> None:
        super().__init__(message=message, status_code=401)


class ModelNotAllowedError(MediCareError):
    """Raised when an unapproved or unconfigured model is requested."""

    def __init__(self, model_name: str) -> None:
        super().__init__(
            message=f"Model '{model_name}' not allowed.",
            status_code=400,
        )


class ReservedParameterError(MediCareError):
    """Raised when reserved internal configuration keys are supplied."""

    def __init__(self, reserved_key: str) -> None:
        super().__init__(
            message=f"Key '{reserved_key}' is reserved.",
            status_code=422,
        )


class SecurityViolationError(MediCareError):
    """Raised when input violates content moderation or prompt injection guardrails."""

    def __init__(self, violations: list[str]) -> None:
        cats = ", ".join(violations)
        super().__init__(
            message=f"Safety guardrail triggered: [{cats}]",
            status_code=400,
        )
        self.violations = violations


class AgentNotFoundError(MediCareError):
    """Raised when the specified agent identifier does not exist in registry."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(
            message=f"Agent '{agent_id}' not found.",
            status_code=404,
        )


class ThreadNotFoundError(MediCareError):
    """Raised when a specified thread history cannot be located."""

    def __init__(self, thread_id: str) -> None:
        super().__init__(
            message=f"Thread '{thread_id}' not found.",
            status_code=404,
        )


class StepBudgetDepletedError(MediCareError):
    """Raised when an agent depletes its step allocation before completion."""

    def __init__(self, max_steps: int) -> None:
        super().__init__(
            message=f"Execution step limit ({max_steps}) depleted before completion.",
            status_code=429,
        )


class InterruptRequiredException(Exception):
    """Internal signal when graph execution suspends to prompt the human."""

    def __init__(self, prompt: str, key: str = "clarification") -> None:
        super().__init__(prompt)
        self.prompt = prompt
        self.key = key


class SQLExecutionError(MediCareError):
    """Raised when SQL execution fails in the sandboxed database tool."""

    def __init__(self, message: str, kind: str = "other") -> None:
        super().__init__(message=message, status_code=400)
        self.kind = kind  # syntax | no_such_table | no_such_column | forbidden | timeout | other


class DocumentLoaderError(MediCareError):
    """Raised when a document cannot be loaded or parsed."""

    def __init__(self, message: str = "Failed to load document") -> None:
        super().__init__(message=message, status_code=400)


class UnsupportedFileTypeError(MediCareError):
    """Raised when an uploaded or ingested file extension is not supported."""

    def __init__(self, ext: str = "unknown") -> None:
        super().__init__(message=f"Unsupported document file type: '{ext}'", status_code=400)


class EmptyDatabaseError(MediCareError):
    """Raised when the database does not exist or all tables are empty."""

    def __init__(self, message: str = "Database is empty.") -> None:
        super().__init__(message=message, status_code=200)


class ProviderUnavailableError(MediCareError):
    """Raised when foundational model provider fails or is unreachable."""

    def __init__(self, message: str = "LLM provider is currently unavailable.") -> None:
        super().__init__(message=message, status_code=503)
