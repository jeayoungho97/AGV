from __future__ import annotations

from pathlib import Path

from openai import OpenAI

try:  # script-mode support
    from openai_utils import optional_env, require_env
except ImportError:
    from .openai_utils import optional_env, require_env


def transcribe_audio_file(audio_path: Path) -> str:
    """
    Speech-to-text using OpenAI Audio Transcriptions API.

    Notes:
    - Provide a pre-recorded audio file (e.g. .wav/.mp3/.m4a).
    - Set OPENAI_API_KEY in your environment.
    """
    api_key = require_env("OPENAI_API_KEY")
    model = optional_env("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")

    client = OpenAI(api_key=api_key)
    with audio_path.open("rb") as f:
        result = client.audio.transcriptions.create(model=model, file=f)

    text = (getattr(result, "text", None) or "").strip()
    if not text:
        raise RuntimeError("Empty transcription result")
    return text
