#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from twitcho.programs import run_silent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-encode one directory of videos as 720p H.264 mezzanine files."
    )
    parser.add_argument("input_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()

    reencode_directory(args.input_directory, args.output_directory)


def reencode_directory(input_directory: Path, output_directory: Path) -> None:
    if not input_directory.is_dir():
        sys.exit(f"{input_directory} is not a directory")
    if output_directory.exists() and not output_directory.is_dir():
        sys.exit(f"{output_directory} is not a directory")

    output_directory.mkdir(exist_ok=True)
    for video in sorted(p for p in input_directory.iterdir() if p.is_file()):
        reencode_video(video, output_directory / f"{video.stem}.mp4")


def reencode_video(video: Path, output: Path) -> None:
    if output.exists():
        sys.exit(f"{output} already exists")

    print(f"Re-encoding {video} to {output}...")
    run_silent(reencode_command(video, output))


def reencode_command(video: Path, output: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-i",
        video.as_posix(),
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
        output.as_posix(),
    ]


if __name__ == "__main__":
    main()
