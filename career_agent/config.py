import json
from dataclasses import dataclass
from pathlib import Path

from .paths import CONFIG_PATH


@dataclass(frozen=True)
class SpeechConfig:
    base_url: str
    health_path: str
    transcription_path: str
    remote_model: str
    local_model: str
    language: str
    connect_timeout_seconds: float
    transcription_timeout_seconds: float


@dataclass(frozen=True)
class Settings:
    speech: SpeechConfig


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Settings(speech=SpeechConfig(**raw["speech"]))
