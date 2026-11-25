"""Authentication and authorization middleware for MediCare."""

from fastapi import Header

from medicare.config import settings
from medicare.domain.errors import AuthenticationRequiredError


async def verify_bearer_auth(authorization: str | None = Header(None)) -> None:
    """Validate incoming Bearer token against configured service secret.

    When SERVICE_SECRET_KEY is None or empty, authentication is disabled and
    requests proceed without error.
    """
    secret = settings.SERVICE_SECRET_KEY
    if not secret:
        return

    if not authorization:
        raise AuthenticationRequiredError("Authorization header missing")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationRequiredError(
            "Invalid Authorization header format. Expected 'Bearer <token>'"
        )

    token = parts[1]
    if token != secret:
        raise AuthenticationRequiredError("Invalid Bearer secret key")
