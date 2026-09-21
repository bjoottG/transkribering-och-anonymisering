"""Nyckelbildsextraktion ur film: ffmpeg-scendetektering + intervall-fallback + dedup.

Skärminspelningar är mestadels stillastående, så scendetekteringströskeln är låg
(en dialogruta som öppnas ändrar bara några procent av pixlarna). Nästan identiska
bilder filtreras bort med perceptuell hash (dHash) innan de skickas till vision-modellen
— det är den viktigaste kostnadsbesparingen.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import settings
from app.jobs import UserVisibleError

logger = logging.getLogger(__name__)

# Längsta bildsida som skickas till modellen (API:t skalar ändå ner större bilder)
MAX_FRAME_WIDTH = 1568
# Max hammingavstånd (av 64 bitar) för att två bilder ska räknas som dubbletter
DEDUP_DISTANCE = 4


@dataclass
class Frame:
    time: float  # sekunder in i filmen
    path: Path


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise UserVisibleError(
            "ffmpeg hittades inte på servern. Installera ffmpeg och starta om applikationen."
        )
    return path


def _ffprobe_duration(video: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is not None:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass
    # Fallback: läs Duration ur ffmpeg-huvudet
    result = subprocess.run([_ffmpeg(), "-i", str(video)], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise UserVisibleError("Filmens längd kunde inte läsas — filen kan vara skadad.")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _extract_scene_frames(video: Path, out_dir: Path, threshold: float) -> list:
    """Bilder vid scenbyten. Returnerar list[Frame] med tider ur showinfo-loggen."""
    pattern = str(out_dir / "scen_%05d.png")
    scale = f"scale='min({MAX_FRAME_WIDTH},iw)':-2"

    def run(vfr_args: list) -> subprocess.CompletedProcess:
        command = [
            _ffmpeg(), "-y", "-i", str(video),
            "-vf", f"select='gt(scene,{threshold})',showinfo,{scale}",
            *vfr_args, pattern,
        ]
        return subprocess.run(command, capture_output=True, text=True)

    result = run(["-fps_mode", "vfr"])
    if result.returncode != 0 and "Unrecognized option 'fps_mode'" in result.stderr:
        result = run(["-vsync", "vfr"])  # ffmpeg äldre än 5.1
    if result.returncode != 0:
        logger.error("ffmpeg scendetektering misslyckades: %s", result.stderr[-2000:])
        raise UserVisibleError("Bildrutor kunde inte extraheras ur filmen.")
    times = [float(t) for t in re.findall(r"pts_time:\s*([\d.]+)", result.stderr)]
    files = sorted(out_dir.glob("scen_*.png"))
    return [Frame(time=times[i] if i < len(times) else 0.0, path=f) for i, f in enumerate(files)]


def _grab_frame(video: Path, at: float, target: Path) -> Optional[Frame]:
    scale = f"scale='min({MAX_FRAME_WIDTH},iw)':-2"
    command = [
        _ffmpeg(), "-y", "-ss", f"{at:.2f}", "-i", str(video),
        "-frames:v", "1", "-vf", scale, str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not target.is_file():
        return None
    return Frame(time=at, path=target)


def _dhash(path: Path) -> int:
    """64-bitars perceptuell dHash (differenshash) med Pillow."""
    from PIL import Image

    with Image.open(path) as image:
        gray = image.convert("L").resize((9, 8), Image.LANCZOS)
        pixels = list(gray.getdata())
    value = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            value = (value << 1) | (1 if left > right else 0)
    return value


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def dedupe_frames(frames: list, max_distance: int = DEDUP_DISTANCE) -> list:
    """Ta bort bilder som är nästan identiska med närmast föregående behållna bild."""
    kept: list = []
    previous_hash: Optional[int] = None
    for frame in sorted(frames, key=lambda f: f.time):
        frame_hash = _dhash(frame.path)
        if previous_hash is not None and hamming(frame_hash, previous_hash) <= max_distance:
            frame.path.unlink(missing_ok=True)
            continue
        kept.append(frame)
        previous_hash = frame_hash
    return kept


def subsample(frames: list, limit: int) -> list:
    """Behåll högst `limit` bilder, jämnt fördelade över tidslinjen."""
    if len(frames) <= limit:
        return frames
    step = len(frames) / limit
    picked = {int(i * step) for i in range(limit)}
    result = []
    for index, frame in enumerate(frames):
        if index in picked:
            result.append(frame)
        else:
            frame.path.unlink(missing_ok=True)
    return result


def extract_keyframes(video: Path, out_dir: Path) -> list:
    """Extrahera nyckelbilder: scenbyten + intervall-fallback, dedupade. list[Frame]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = _ffprobe_duration(video)

    frames = _extract_scene_frames(video, out_dir, settings.scene_threshold)

    # Fallback-intervall: fyll luckor där inget scenbyte fångats.
    # Starten anpassas till korta filmer så att minst en bild alltid tas.
    interval = max(settings.frame_interval, 1)
    covered = sorted(frame.time for frame in frames)
    t = min(interval, max(duration - 0.5, 0.1)) / 2
    index = 0
    while t < duration:
        if not any(abs(t - c) < interval / 2 for c in covered):
            grabbed = _grab_frame(video, t, out_dir / f"intervall_{index:05d}.png")
            if grabbed is not None:
                frames.append(grabbed)
                index += 1
        t += interval

    frames = dedupe_frames(frames)
    frames = subsample(frames, settings.frame_max)
    logger.info("Extraherade %d nyckelbilder ur %s (%.0f s)", len(frames), video.name, duration)
    return frames
