import subprocess as sp
from pathlib import Path

import pytest

from scripts import reencode_videos


def test_reencode_command_uses_mezzanine_settings() -> None:
    command = reencode_videos.reencode_command(Path("source.mov"), Path("out.mp4"))

    assert command == [
        "ffmpeg",
        "-hide_banner",
        "-i",
        "source.mov",
        "-vf",
        "scale=1280:-2,fps=30",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "out.mp4",
    ]


def test_reencode_directory_writes_mp4_files_to_output_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    (source / "a.mov").write_text("a")
    (source / "b.mp4").write_text("b")
    (source / "subdir").mkdir()
    commands: list[list[str]] = []

    def run_silent(command: list[str], *, text: bool = False) -> sp.CompletedProcess:
        commands.append(command)
        Path(command[-1]).write_text("encoded")
        return sp.CompletedProcess(command, 0)

    monkeypatch.setattr(reencode_videos, "run_silent", run_silent)

    reencode_videos.reencode_directory(source, output)

    assert [c[-1] for c in commands] == [
        (output / "a.mp4").as_posix(),
        (output / "b.mp4").as_posix(),
    ]
    assert (output / "a.mp4").read_text() == "encoded"
    assert (output / "b.mp4").read_text() == "encoded"


def test_reencode_video_rejects_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.mov"
    output = tmp_path / "output.mp4"
    source.touch()
    output.touch()

    with pytest.raises(SystemExit, match="already exists"):
        reencode_videos.reencode_video(source, output)
