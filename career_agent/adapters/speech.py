from pathlib import Path

import httpx

from ..config import SpeechConfig
from ..domain.models import TranscriptionResult


class RemoteUnavailable(RuntimeError):
    pass


class RemoteSpeachesBackend:
    def __init__(self, config: SpeechConfig):
        self.config = config

    def is_available(self) -> bool:
        try:
            response = httpx.get(
                self.config.base_url + self.config.health_path,
                timeout=self.config.connect_timeout_seconds,
            )
            return response.status_code == 200
        except httpx.TransportError:
            return False

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        timeout = httpx.Timeout(
            self.config.transcription_timeout_seconds,
            connect=self.config.connect_timeout_seconds,
        )
        try:
            with audio_path.open("rb") as audio:
                response = httpx.post(
                    self.config.base_url + self.config.transcription_path,
                    data={
                        "model": self.config.remote_model,
                        "language": self.config.language,
                        "response_format": "json",
                        "vad_filter": "true",
                    },
                    files={"file": (audio_path.name, audio, "application/octet-stream")},
                    timeout=timeout,
                )
        except httpx.TransportError as error:
            raise RemoteUnavailable(str(error)) from error
        if response.status_code >= 500:
            raise RemoteUnavailable(f"speech-сервис вернул HTTP {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        text = payload if isinstance(payload, str) else payload.get("text", "")
        if not text.strip():
            raise RuntimeError("speech-сервис вернул пустую транскрипцию")
        return TranscriptionResult(text.strip(), "remote", self.config.remote_model)


class LocalWhisperBackend:
    def __init__(self, config: SpeechConfig):
        self.config = config

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "Локальный fallback требует faster-whisper. "
                "Установите его командой: python -m pip install -e '.[speech]'"
            ) from error
        model = WhisperModel(
            self.config.local_model, device="cpu", compute_type="int8", cpu_threads=8,
        )
        segments, _ = model.transcribe(str(audio_path), language=self.config.language)
        text = " ".join(segment.text for segment in segments).strip()
        return TranscriptionResult(text, "local", self.config.local_model)
