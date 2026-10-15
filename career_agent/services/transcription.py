from pathlib import Path

from ..adapters.speech import LocalWhisperBackend, RemoteSpeachesBackend, RemoteUnavailable
from ..domain.models import TranscriptionResult


class TranscriptionService:
    def __init__(self, remote: RemoteSpeachesBackend, local: LocalWhisperBackend):
        self.remote = remote
        self.local = local

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        if self.remote.is_available():
            try:
                return self.remote.transcribe(audio_path)
            except RemoteUnavailable:
                pass
        return self.local.transcribe(audio_path)
