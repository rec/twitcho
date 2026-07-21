#!/usr/bin/env python3
import argparse
import shutil
import subprocess as sp
import sys
import tempfile
from pathlib import Path

from scripts import loop_videos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview videos as forward/backward loops before accepting them."
    )
    parser.add_argument("videos", nargs="+", type=Path)
    args = parser.parse_args()

    for video in args.videos:
        test_loop(video)


def test_loop(video: Path) -> None:
    if not video.exists():
        sys.exit(f"{video} does not exist")
    if loop_videos.looped_path(video).exists():
        sys.exit(f"{loop_videos.looped_path(video)} already exists")

    with tempfile.TemporaryDirectory(prefix="twitcho-loop-test-") as directory:
        preview = Path(directory) / loop_videos.looped_path(video).name
        write_loop(video, preview)
        while True:
            play_preview(preview)
            answer = input(f"{video} [r=replay, l=loop, return=skip] ").strip().lower()
            if answer == "r":
                continue
            if answer == "l":
                accept_loop(video, preview)
                return
            if answer == "":
                return
            print("Please enter r, l, or return.", file=sys.stderr)


def write_loop(video: Path, output: Path) -> None:
    frame_count = loop_videos.count_frames(video)
    if frame_count < 3:
        sys.exit(f"{video} has fewer than 3 frames")
    sp.run(loop_videos.ffmpeg_command(video, output, frame_count), check=True)


def play_preview(video: Path) -> None:
    sp.run(preview_command(video), check=True)


def preview_command(video: Path) -> list[str]:
    return [
        "ffplay",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-autoexit",
        "-loop",
        "0",
        "-t",
        "10",
        video.as_posix(),
    ]


def accept_loop(video: Path, preview: Path) -> None:
    output = loop_videos.looped_path(video)
    originals = video.parent / "originals"
    originals.mkdir(exist_ok=True)
    target = originals / video.name
    if target.exists():
        sys.exit(f"{target} already exists")
    shutil.move(preview.as_posix(), output.as_posix())
    shutil.move(video.as_posix(), target.as_posix())


if __name__ == "__main__":
    main()
