"""Tester för skärmbildsbeskrivning och tidslinje. Claude API mockas via describe_fn."""
from __future__ import annotations

from app.docx_output import merge_timeline
from app.frames import Frame
from app.vision import describe_frames


def _frames(tmp_path, count):
    result = []
    for i in range(count):
        path = tmp_path / f"bild_{i}.png"
        path.write_bytes(b"png" + bytes([i]))
        result.append(Frame(time=float(i * 10), path=path))
    return result


def test_describe_frames_med_mock(tmp_path):
    frames = _frames(tmp_path, 3)
    seen = []

    def fake_describe(png_bytes):
        seen.append(png_bytes)
        return f"Beskrivning {len(seen)}"

    progress = []
    result = describe_frames(frames, progress=progress.append, describe_fn=fake_describe)
    assert [r["text"] for r in result] == ["Beskrivning 1", "Beskrivning 2", "Beskrivning 3"]
    assert [r["time"] for r in result] == [0.0, 10.0, 20.0]
    assert len(seen) == 3 and seen[0] == b"png\x00"
    assert progress[-1] == 1.0


def test_describe_frames_tom_lista():
    assert describe_frames([], describe_fn=lambda b: "x") == []


def test_merge_timeline_sorterar_pa_tid():
    segments = [
        {"start": 0.0, "end": 4.0, "text": "Hej och välkomna."},
        {"start": 12.0, "end": 16.0, "text": "Klicka på Komplettering."},
    ]
    descriptions = [
        {"time": 5.0, "text": "Startsidan visas."},
        {"time": 13.0, "text": "Fliken Komplettering är öppen."},
    ]
    events = merge_timeline(segments, descriptions)
    assert [(e["time"], e["kind"]) for e in events] == [
        (0.0, "tal"), (5.0, "skärm"), (12.0, "tal"), (13.0, "skärm"),
    ]


def test_merge_timeline_hoppar_over_tomt():
    events = merge_timeline([{"start": 0, "end": 1, "text": "  "}], [{"time": 2, "text": ""}])
    assert events == []
