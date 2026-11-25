"""Audit test verifying voice and audio features are strictly excluded from the UI."""

import ast
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UI_DIR = REPO_ROOT / "ui"


def test_app_config_voice_flag_is_false():
    """Verify features.voice is explicitly False in config/app.yaml."""
    cfg_path = REPO_ROOT / "config" / "app.yaml"
    assert cfg_path.exists(), "config/app.yaml not found"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert "features" in data, "Missing 'features' block in app.yaml"
    assert data["features"].get("voice") is False, "features.voice must be False"


def test_no_audio_component_files_exist():
    """Verify audio component files like audio.py are completely removed."""
    audio_file = UI_DIR / "components" / "audio.py"
    assert not audio_file.exists(), "ui/components/audio.py should not exist"


def test_no_speech_or_audio_imports_in_ui():
    """Verify no UI module imports audio, speech, TTS, or STT libraries."""
    forbidden_modules = [
        "speech",
        "audio",
        "pydub",
        "sounddevice",
        "whisper",
        "pyttsx3",
        "gtts",
        "medicare.speech",
        "medicare.tts",
        "medicare.stt",
    ]

    for py_file in UI_DIR.rglob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for f_mod in forbidden_modules:
                        assert f_mod not in alias.name, (
                            f"Forbidden speech import '{alias.name}' found in {py_file}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                for f_mod in forbidden_modules:
                    assert f_mod not in node.module, (
                        f"Forbidden speech import '{node.module}' found in {py_file}"
                    )


def test_no_voice_widgets_or_labels_in_ui_code():
    """Verify no voice toggles, microphone buttons, or voice audio labels remain in UI code."""
    forbidden_terms = [
        "voice_audio_label",
        "enable voice audio",
        "voice_enabled",
        "st.audio",
        "mic_button",
        "microphone",
    ]

    for py_file in UI_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8").lower()
        for term in forbidden_terms:
            assert term not in content, f"Forbidden voice term '{term}' found in {py_file}"
