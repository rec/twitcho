#!/usr/bin/env python3
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from scripts import loop_videos
from twitcho.programs import run_silent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview videos as forward/backward loops before accepting them."
    )
    parser.add_argument("videos", nargs="+", type=Path)
    args = parser.parse_args()

    for video in args.videos:
        if not ignored(video):
            test_loop(video)


def test_loop(video: Path) -> None:
    if ignored(video):
        return
    if not video.exists():
        sys.exit(f"{video} does not exist")
    if loop_videos.looped_path(video).exists():
        sys.exit(f"{loop_videos.looped_path(video)} already exists")

    with tempfile.TemporaryDirectory(prefix="twitcho-loop-test-") as directory:
        preview = Path(directory) / loop_videos.looped_path(video).name
        write_loop(video, preview)
        while True:
            print(f"{video} [r=replay, l=loop, return=skip]")
            play_preview(preview)
            answer = input("> ").strip().lower()
            if answer == "r":
                continue
            if answer == "l":
                accept_loop(video, preview)
                return
            if answer == "":
                return
            print("Please enter r, l, or return.", file=sys.stderr)


def ignored(video: Path) -> bool:
    return "looped" in video.name.lower()


def write_loop(video: Path, output: Path) -> None:
    frame_count = loop_videos.count_frames(video)
    if frame_count < 3:
        sys.exit(f"{video} has fewer than 3 frames")
    run_silent(loop_videos.ffmpeg_command(video, output, frame_count))


def play_preview(video: Path) -> None:
    run_silent(preview_command(video, duration=duration(video)))


def preview_command(video: Path, *, duration: float) -> list[str]:
    start = max(0.0, duration - 2.0)
    return [
        "ffplay",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-autoexit",
        "-loop",
        "0",
        "-ss",
        f"{start:.3f}",
        "-t",
        "4",
        video.as_posix(),
    ]


def duration(video: Path) -> float:
    result = run_silent(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            video.as_posix(),
        ],
        text=True,
    )
    return float(result.stdout.strip())


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
