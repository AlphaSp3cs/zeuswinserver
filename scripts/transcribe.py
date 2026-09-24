#!/usr/bin/env python3
"""
transcribe.py - offline speech-to-text CLI.
Primary: faster-whisper
Fallback: openai-whisper if faster-whisper backend fails on this machine.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("CTRANSLATE2_NO_CUDA", "1")


def _transcribe_faster(audio_path: Path, model_name: str, compute_type: str, language: str | None) -> str:
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
        vad_filter=True,
    )
    parts = [seg.text.strip() for seg in segments if seg.text and seg.text.strip()]
    return " ".join(parts).strip()


def _transcribe_openai(audio_path: Path, model_name: str, language: str | None) -> str:
    import whisper  # openai-whisper
    model = whisper.load_model(model_name, device="cpu")
    result = model.transcribe(
        str(audio_path),
        language=language,
        fp16=False,
    )
    return (result.get("text") or "").strip()


def transcribe(audio_path: str | Path, model_name: str = "base", compute_type: str = "int8", language: str | None = None) -> str:
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    last_err: Exception | None = None
    for name, fn in [
        ("faster-whisper", lambda: _transcribe_faster(audio_path, model_name, compute_type, language)),
        ("openai-whisper", lambda: _transcribe_openai(audio_path, model_name, language)),
    ]:
        try:
            return fn()
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All backends failed; last error: {last_err}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline transcription")
    ap.add_argument("audio", help="Path to audio file")
    ap.add_argument("--model", default="base", help="Whisper model size")
    ap.add_argument("--compute-type", default="int8", help="faster-whisper compute type")
    ap.add_argument("--language", default=None, help="ISO language code")
    args = ap.parse_args(argv)

    text = transcribe(args.audio, args.model, args.compute_type, args.language)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
