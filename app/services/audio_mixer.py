"""Mix a finished video with a background music track.

Strategy: loop the music to match video length, compress the music with the
video audio as a side-chain trigger ("ducking"), then amix at balanced levels.
Falls back to a plain volume mix if sidechain fails.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import FFMPEG_BIN, TEMP_DIR
from app.services.ffmpeg_service import _get_duration


def mix_with_music(
    video_path: str,
    music_path: str,
    output_path: str,
    video_volume: float = 0.55,
    music_volume: float = 0.45,
    fade_in: float = 1.0,
    fade_out: float = 2.0,
) -> str:
    """Produce ``output_path`` = video + ducked background music."""
    video_dur = _get_duration(video_path)
    if video_dur <= 0:
        raise RuntimeError("Video suresi okunamadi")

    fade_out_start = max(0.0, video_dur - fade_out)

    music_chain = (
        f"[1:a]aloop=loop=-1:size=2e9,"
        f"atrim=duration={video_dur:.3f},"
        f"asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade_in:.2f},"
        f"afade=t=out:st={fade_out_start:.2f}:d={fade_out:.2f},"
        f"volume={music_volume}"
        f"[music]"
    )
    video_chain = f"[0:a]volume={video_volume}[vaud]"

    # Sidechain: [vaud] triggers compressor on [music]
    ducked_chain = (
        "[music][vaud]sidechaincompress="
        "threshold=0.03:ratio=8:attack=20:release=250:makeup=1:mix=1[ducked]"
    )
    mix_chain = "[vaud][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
    filter_complex = ";".join([music_chain, video_chain, ducked_chain, mix_chain])

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode == 0:
        return output_path

    # Fallback: simple amix without sidechain (some ffmpeg builds lack it)
    fallback_filter = ";".join([
        music_chain,
        video_chain,
        "[vaud][music]amix=inputs=2:duration=first:normalize=0[aout]",
    ])
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", fallback_filter,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-shortest",
        output_path,
    ]
    result2 = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if result2.returncode != 0:
        raise RuntimeError(f"Muzik karisimi hatasi: {result2.stderr[-500:]}")
    return output_path


def temp_path(batch_id: str, suffix: str = "_mixed.mp4") -> str:
    return str(TEMP_DIR / f"batch_{batch_id}{suffix}")
