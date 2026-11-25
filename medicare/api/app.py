"""FastAPI Gateway Application Factory with Lifespan and Middleware."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from medicare.api.routes.agui import router as agui_router
from medicare.api.routes.documents import router as documents_router
from medicare.api.routes.feedback import router as feedback_router
from medicare.api.routes.info import router as info_router
from medicare.api.routes.invoke import router as invoke_router
from medicare.api.routes.medicare import router as medicare_router
from medicare.api.routes.stream import router as stream_router
from medicare.api.routes.threads import router as threads_router
from medicare.config import settings
from medicare.domain.errors import (
    MediCareError,
)
from medicare.domain.protocols import CheckpointStoreProtocol, MemoryStoreProtocol
from medicare.storage.checkpointer import InMemoryCheckpointer, SqliteCheckpointer
from medicare.storage.memory_store import InMemoryMemoryStore

# Module-level instances for persistence
_global_checkpointer: CheckpointStoreProtocol = InMemoryCheckpointer()
_global_memory_store: MemoryStoreProtocol = InMemoryMemoryStore()


def get_app_checkpointer() -> CheckpointStoreProtocol:
    return _global_checkpointer


def get_app_memory_store() -> MemoryStoreProtocol:
    return _global_memory_store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan manager initializing persistence layer on startup."""
    global _global_checkpointer, _global_memory_store

    if settings.STORAGE_ENGINE == "sqlite":
        _global_checkpointer = SqliteCheckpointer(db_path=settings.SQLITE_PATH)
        await _global_checkpointer.initialize()
    else:
        _global_checkpointer = InMemoryCheckpointer()

    _global_memory_store = InMemoryMemoryStore()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI Gateway Application."""
    app = FastAPI(
        title="MediCare Multi-Agent Gateway",
        description="Enterprise Multi-Agent Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        # allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Domain Exception Handlers
    @app.exception_handler(MediCareError)
    async def domain_error_handler(request: Request, exc: MediCareError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "message": exc.message},
        )

    # Mount Routers
    app.include_router(info_router)
    app.include_router(medicare_router)
    app.include_router(documents_router)
    app.include_router(invoke_router)
    app.include_router(stream_router)
    app.include_router(threads_router)
    app.include_router(feedback_router)
    app.include_router(agui_router)

    return app
