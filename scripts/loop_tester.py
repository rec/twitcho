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
        if ignored(video):
            print(f"Moving existing loop {video} into {loops_directory(video)}/")
            move_to_loops(video)
        else:
            test_loop(video)


def test_loop(video: Path) -> None:
    if ignored(video):
        print(f"Moving existing loop {video} into {loops_directory(video)}/")
        move_to_loops(video)
        return
    if not video.exists():
        sys.exit(f"{video} does not exist")
    if looped_output(video).exists():
        sys.exit(f"{looped_output(video)} already exists")

    with tempfile.TemporaryDirectory(prefix="twitcho-loop-test-") as directory:
        preview = Path(directory) / loop_videos.looped_path(video).name
        playback = Path(directory) / f"{preview.stem}-preview{preview.suffix}"
        print(f"Converting {video} into a temporary loop preview...")
        write_loop(video, preview)
        print(f"Preparing playback preview for {video}...")
        write_playback_preview(preview, playback)
        while True:
            print(f"{video} [r=replay, l=loop, return=skip]")
            print(f"Playing preview for {video}...")
            play_preview(playback)
            answer = input("> ").strip().lower()
            if answer == "r":
                continue
            if answer == "l":
                print(f"Moving accepted loop into {loops_directory(video)}/...")
                accept_loop(video, preview)
                return
            if answer == "":
                print(f"Moving skipped file into {loops_directory(video)}/...")
                move_to_loops(video)
                return
            print("Please enter r, l, or return.", file=sys.stderr)


def ignored(video: Path) -> bool:
    return "looped" in video.name.lower()


def loops_directory(video: Path) -> Path:
    return video.parent / "loops"


def looped_output(video: Path) -> Path:
    return loops_directory(video) / loop_videos.looped_path(video).name


def move_to_loops(video: Path) -> Path:
    if not video.exists():
        sys.exit(f"{video} does not exist")
    if video.parent.name == "loops":
        return video
    loops = loops_directory(video)
    loops.mkdir(exist_ok=True)
    target = loops / video.name
    if target.exists():
        sys.exit(f"{target} already exists")
    shutil.move(video.as_posix(), target.as_posix())
    return target


def write_loop(video: Path, output: Path) -> None:
    frame_count = loop_videos.count_frames(video)
    if frame_count < 3:
        sys.exit(f"{video} has fewer than 3 frames")
    run_silent(loop_videos.ffmpeg_command(video, output, frame_count))


def play_preview(video: Path) -> None:
    run_silent(preview_command(video))


def write_playback_preview(video: Path, output: Path) -> None:
    run_silent(playback_preview_command(video, output, duration=duration(video)))


def playback_preview_command(
    video: Path, output: Path, *, duration: float
) -> list[str]:
    start = max(0.0, duration - 2.0)
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        video.as_posix(),
        "-t",
        "4",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output.as_posix(),
    ]


def preview_command(video: Path) -> list[str]:
    return [
        "ffplay",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-autoexit",
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
    output = looped_output(video)
    output.parent.mkdir(exist_ok=True)
    originals = video.parent / "originals"
    originals.mkdir(exist_ok=True)
    target = originals / video.name
    if target.exists():
        sys.exit(f"{target} already exists")
    shutil.move(preview.as_posix(), output.as_posix())
    shutil.move(video.as_posix(), target.as_posix())


if __name__ == "__main__":
    main()
