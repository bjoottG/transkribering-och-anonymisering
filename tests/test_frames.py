"""Tester för nyckelbildsextraktion: dHash-dedup och subsampling. ffmpeg-steget testas separat."""
from __future__ import annotations

import shutil

import pytest

from app.frames import Frame, dedupe_frames, extract_keyframes, hamming, subsample


def _make_png(path, color, text_row=None):
    from PIL import Image

    image = Image.new("RGB", (320, 240), color)
    if text_row is not None:  # rita en avvikande rad så bilden skiljer sig tydligt
        for x in range(320):
            image.putpixel((x, text_row), (0, 0, 0))
        for x in range(0, 320, 3):
            for y in range(60, 180):
                image.putpixel((x, y), (255 - x % 255, 0, 0))
    image.save(path)
    return path


def test_dedupe_tar_bort_identiska(tmp_path):
    frames = [
        Frame(time=0.0, path=_make_png(tmp_path / "a.png", (200, 200, 200))),
        Frame(time=5.0, path=_make_png(tmp_path / "b.png", (200, 200, 200))),  # dubblett
        Frame(time=10.0, path=_make_png(tmp_path / "c.png", (30, 30, 30), text_row=100)),
    ]
    kept = dedupe_frames(frames)
    assert [f.time for f in kept] == [0.0, 10.0]
    assert not (tmp_path / "b.png").exists()  # dubbletten raderas


def test_dedupe_behaller_olika(tmp_path):
    frames = [
        Frame(time=0.0, path=_make_png(tmp_path / "a.png", (255, 255, 255))),
        Frame(time=5.0, path=_make_png(tmp_path / "b.png", (10, 10, 10), text_row=50)),
    ]
    assert len(dedupe_frames(frames)) == 2


def test_hamming():
    assert hamming(0b1010, 0b1010) == 0
    assert hamming(0b1010, 0b0101) == 4


def test_subsample_behaller_alla_under_gransen(tmp_path):
    frames = [Frame(time=float(i), path=_make_png(tmp_path / f"{i}.png", (i * 20, 0, 0))) for i in range(3)]
    assert len(subsample(frames, 10)) == 3


def test_subsample_glesar_ut_jamnt(tmp_path):
    frames = [Frame(time=float(i), path=_make_png(tmp_path / f"{i}.png", (i % 255, 0, 0))) for i in range(20)]
    kept = subsample(frames, 5)
    assert len(kept) == 5
    assert kept[0].time == 0.0
    assert sum(1 for i in range(20) if (tmp_path / f"{i}.png").exists()) == 5


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg saknas")
def test_extract_keyframes_ur_riktig_film(tmp_path):
    import subprocess

    video = tmp_path / "test.mp4"
    subprocess.run(
        [shutil.which("ffmpeg"), "-y",
         "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=5",
         "-pix_fmt", "yuv420p", str(video)],
        capture_output=True, check=True,
    )
    frames = extract_keyframes(video, tmp_path / "bilder")
    assert frames, "minst en nyckelbild förväntas"
    assert all(f.path.is_file() for f in frames)
    assert all(0 <= f.time <= 4.5 for f in frames)
