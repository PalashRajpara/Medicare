"""Test verifying dynamic text customization through YAML configuration.

Demonstrates that changing values in config/messages.yaml and config/app.yaml
in a temporary copy immediately reflects in msg() and get_app_config() upon clearing config cache,
with zero code modifications required.
"""

import yaml

from medicare.config import settings
from medicare.config_loader import (
    clear_config_cache,
    get_app_config,
    msg,
)


def test_dynamic_message_text_customization(tmp_path, monkeypatch):
    """Verify that msg() dynamically returns overridden text from a custom messages.yaml."""
    custom_messages = {
        "conversational_welcome": "Custom Hospital Bot Welcome: How can we assist you today?",
        "custom_alert": "Custom alert for patient {patient_name} in ward {ward_id}.",
    }
    msg_yaml = tmp_path / "messages.yaml"
    msg_yaml.write_text(yaml.safe_dump(custom_messages), encoding="utf-8")

    monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path))
    clear_config_cache()

    updated_welcome = msg("conversational_welcome")
    assert updated_welcome == "Custom Hospital Bot Welcome: How can we assist you today?"

    interpolated = msg("custom_alert", patient_name="Alice", ward_id="4B")
    assert interpolated == "Custom alert for patient Alice in ward 4B."

    clear_config_cache()


def test_dynamic_app_config_customization(tmp_path, monkeypatch):
    """Verify that get_app_config() dynamically reflects changes in a custom app.yaml."""
    custom_cfg = {
        "app_name": "Metro Health AI Navigator",
        "currency_symbol": "$",
        "currency_code": "USD",
        "ui": {
            "page_title": "Metro Health AI Navigator | Portal",
            "table_header_hospitals": "Hospital Cost Breakdown",
        },
    }
    app_yaml = tmp_path / "app.yaml"
    app_yaml.write_text(yaml.safe_dump(custom_cfg), encoding="utf-8")

    monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path))
    clear_config_cache()

    cfg = get_app_config()
    assert cfg["app_name"] == "Metro Health AI Navigator"
    assert cfg["currency_symbol"] == "$"
    assert cfg["ui"]["table_header_hospitals"] == "Hospital Cost Breakdown"

    clear_config_cache()
