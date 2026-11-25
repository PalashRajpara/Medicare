"""Configuration and settings tests."""

from medicare.config import Settings


def test_default_settings():
    s = Settings(_env_file=None)
    assert s.HOST == "0.0.0.0"
    assert s.PORT == 8080
    assert s.DEFAULT_AGENT == "medicare-navigator"
    assert "mock-gpt-4" in s.ALLOWED_MODELS
    assert s.USE_MOCK_MODELS is True


def test_allowed_models_validation():
    s = Settings(ALLOWED_MODELS=["custom-llm-1", "custom-llm-2"])
    assert len(s.ALLOWED_MODELS) == 2
    assert "custom-llm-1" in s.ALLOWED_MODELS
