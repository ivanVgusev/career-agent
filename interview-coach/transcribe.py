#!/usr/bin/env python3
"""Compatibility CLI for remote-first transcription with local fallback."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from career_agent.adapters.speech import LocalWhisperBackend, RemoteSpeachesBackend
from career_agent.config import load_settings
from career_agent.services.transcription import TranscriptionService


RAW_DIR = Path(__file__).resolve().parent / "transcripts" / "raw"


def transcribe(input_file_path: str, output_name: str) -> str:
    source = Path(input_file_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    safe_name = Path(output_name).name
    settings = load_settings()
    service = TranscriptionService(
        RemoteSpeachesBackend(settings.speech), LocalWhisperBackend(settings.speech),
    )
    result = service.transcribe(source)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output = RAW_DIR / f"{safe_name}.txt"
    temporary = output.with_suffix(".txt.tmp")
    temporary.write_text(result.text, encoding="utf-8")
    temporary.replace(output)
    print(f"backend={result.backend} | model={result.model}")
    return str(output)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Использование: python transcribe.py <input_audio> <output_name>")
        raise SystemExit(1)
    print(f"Готово: {transcribe(sys.argv[1], sys.argv[2])}")
