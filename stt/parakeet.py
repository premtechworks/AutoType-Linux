"""Local Parakeet STT via transcribe.cpp (offline, no internet).

CLI output format (verified against transcribe-cli): the transcript is on
the `text: ...` line — NOT the last line (that's `realtime: ...`).
We run with `-q --timestamps none` for minimal, stable output.
"""
import subprocess
from pathlib import Path

from .base import Transcriber


class ParakeetTranscriber(Transcriber):
    def __init__(self, binary_path: str, model_path: str):
        self.binary_path = Path(binary_path)
        self.model_path = Path(model_path)
        if not self.binary_path.exists():
            raise RuntimeError(f"Parakeet binary not found: {self.binary_path}")
        if not self.model_path.exists():
            raise RuntimeError(f"Parakeet model not found: {self.model_path}")

    def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        command = [
            str(self.binary_path),
            "-q",
            "--timestamps", "none",
            "-m", str(self.model_path),
            str(path),
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Parakeet transcription timed out: {exc}") from exc
        except OSError as exc:
            raise RuntimeError(f"Could not run Parakeet binary: {exc}") from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"Parakeet failed (exit {result.returncode}): "
                f"{result.stderr.strip()[-500:]}"
            )
        return self._parse_transcript(result.stdout)

    @staticmethod
    def _parse_transcript(stdout: str) -> str:
        for line in stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("text:"):
                return stripped[len("text:"):].strip()
        raise RuntimeError(
            f"No transcript in Parakeet output: {stdout.strip()[-500:]}"
        )
