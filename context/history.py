"""Persistent utterance history (JSONL). Never breaks the pipeline on failure."""
import json
import time
from pathlib import Path

DEFAULT_LIMIT = 500


class History:
    def __init__(self, path: Path, limit: int = DEFAULT_LIMIT):
        self.path = Path(path)
        self.limit = limit
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def append(self, entry: dict) -> None:
        try:
            entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._prune()
        except Exception:
            pass  # history must never break dictation

    def _prune(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            if len(lines) > self.limit * 2:
                self.path.write_text(
                    "\n".join(lines[-self.limit:]) + "\n", encoding="utf-8")
        except Exception:
            pass

    def recent_finals(self, n: int = 2) -> list[str]:
        """Last n pasted texts, for continuity in Smart mode."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        finals = []
        for line in reversed(lines[-50:]):
            try:
                final = json.loads(line).get("final") or ""
            except Exception:
                continue
            if final:
                finals.append(final)
            if len(finals) >= n:
                break
        return list(reversed(finals))
