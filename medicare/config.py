"""MediCare Configuration Module."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for MediCare."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server Network & Gateway
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 30

    # Security & Authentication
    SERVICE_SECRET_KEY: str | None = None

    # Model Routing & Defaults
    DEFAULT_AGENT: str = "medicare-navigator"
    DEFAULT_MODEL: str = "mock-gpt-4"
    ALLOWED_MODELS: list[str] = Field(
        default_factory=lambda: [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "mock-gpt-4",
        ]
    )
    USE_MOCK_MODELS: bool = True
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # Commercial & Cloud API Keys
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    DEEPSEEK_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    AWS_BEDROCK_ENABLED: bool = False

    # Local Inference & Daemon
    LOCAL_MODEL_URL: str | None = "http://localhost:8000/v1"
    OLLAMA_BASE_URL: str | None = "http://localhost:11434"

    # Persistence & Checkpointing
    VAR_DIR: str = "var"
    STORAGE_ENGINE: Literal["sqlite", "memory", "postgres", "mongo"] = "sqlite"
    SQLITE_PATH: str = "var/platform.db"
    POSTGRES_DSN: str | None = None
    MONGO_URI: str | None = None

    # MediCare & Claim Navigator Configuration
    MEDICARE_DB_PATH: str = "var/hospitals.db"
    MANIFEST_DB_PATH: str = "var/manifest.db"
    POLICY_DOCS_DIR: str = "data/policies"
    SEED_CSV_DIR: str = "data/seed"
    CHROMA_PATH: str = "var/chroma"
    CHROMA_COLLECTION: str = "insurance_policies"
    AGENT_MAX_STEPS: int = 6
    CONFIG_DIR: str = "config"
    SQL_MAX_RETRIES: int = 3
    SQL_MAX_ROWS: int = 200
    SQL_TIMEOUT_SECONDS: float = 5.0
    RAG_TOP_K: int = 5
    MEDICARE_DEMO_FAIL_FIRST: bool = False
    HELPLINE_EMERGENCY: str = "112"
    HELPLINE_MENTAL_HEALTH: str = "14416 (Tele-MANAS)"

    # LangGraph Runtime
    GRAPH_RECURSION_LIMIT: int = 40
    GRAPH_TIMEOUT_SECONDS: float = 90.0
    MAX_LLM_CALLS_PER_RUN: int = 14
    LANGGRAPH_CHECKPOINTER: Literal["none", "memory", "sqlite"] = "memory"
    LANGGRAPH_CHECKPOINT_PATH: str = "var/langgraph_checkpoints.db"

    # Supervisor Configuration
    SUPERVISOR_USE_LLM: bool = True
    SUPERVISOR_MIN_CONFIDENCE: float = 0.55

    # RAG & Corrective Retrieval
    EMBEDDING_BACKEND: Literal["chroma_default", "hash"] = "chroma_default"
    RAG_CHUNK_CHARS: int = 900
    RAG_CHUNK_OVERLAP: int = 120
    RAG_DENSE_K: int = 20
    RAG_SPARSE_K: int = 20
    RAG_FETCH_K: int = 12
    RAG_MIN_RELEVANT: int = 1
    RAG_MAX_REWRITES: int = 2
    RAG_RRF_K: int = 60
    ENABLE_OCR: bool = False

    # Documents & Uploads
    UPLOAD_DIR: str = "var/uploads"
    UPLOAD_MAX_MB: int = 20
    UPLOAD_MAX_PAGES: int = 300
    USER_DOCS_PER_USER_MAX: int = 25
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = [
        ".pdf",
        ".docx",
        ".md",
        ".txt",
        ".html",
        ".htm",
        ".csv",
    ]

    # Grounding Verifier
    VERIFIER_ENABLED: bool = True
    VERIFIER_MAX_REGENERATIONS: int = 1

    # External Tools & Integrations
    OPENWEATHER_API_KEY: str | None = None
    CLOUD_KB_ID: str | None = None
    REMOTE_MCP_URL: str | None = None
    REMOTE_MCP_TOKEN: str | None = None

    # Observability & Tracing
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "medicare"
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Speech Services
    STT_PROVIDER: str = "mock"
    TTS_PROVIDER: str = "mock"


settings = Settings()
