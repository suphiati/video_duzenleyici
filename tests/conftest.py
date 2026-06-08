"""Shared test setup.

Makes the project root importable regardless of where pytest is launched, and
exposes small helpers for building synthetic media dicts (no real files needed
for the pure-logic tests).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_videos(n: int, duration: float = 30.0) -> list[dict]:
    return [{"path": f"video_{i}.mp4", "duration": duration} for i in range(n)]


def make_photos(n: int) -> list[dict]:
    return [{"path": f"photo_{i}.jpg", "duration": 0} for i in range(n)]
