"""Metadata and service health endpoints."""

from fastapi import APIRouter, Depends

from medicare.agents.registry import registry
from medicare.config import settings
from medicare.config_loader import get_app_config
from medicare.domain.models import AppConfigResponse, HealthResponse, InfoResponse
from medicare.security.auth import verify_bearer_auth
from medicare.telemetry.tracer import telemetry

router = APIRouter(tags=["Metadata & Health"])


@router.get("/app/config", response_model=AppConfigResponse)
async def app_configuration() -> AppConfigResponse:
    """Return UI labels, layout configuration, features, and settings from config/app.yaml."""
    cfg = get_app_config()
    safe_config = {
        k: v
        for k, v in cfg.items()
        if not any(s in k.lower() for s in ("secret", "token", "password", "key", "credential"))
    }
    return AppConfigResponse.model_validate(safe_config)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Infrastructure liveness probe returning service and telemetry connectivity."""
    return HealthResponse(
        status="ok",
        telemetry="connected" if telemetry.is_connected() else "disconnected",
    )


@router.get("/info", response_model=InfoResponse, dependencies=[Depends(verify_bearer_auth)])
async def system_info() -> InfoResponse:
    """Enumerate registered agents, supported foundational models, and defaults."""
    return InfoResponse(
        agents=registry.list_agents(),
        models=settings.ALLOWED_MODELS,
        default_agent=settings.DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )
