#!/usr/bin/env python3
import random
import subprocess as sp
import sys
from pathlib import Path

import tyro
from pydantic import BaseModel

IMAGE_SUFFIXES = {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


class Media(BaseModel):
    path: Path
    duration: float
    is_still: bool = False


class Scene(BaseModel):
    media: Media
    duration: float


class Transition(BaseModel):
    duration: float


class TitleEvent(BaseModel):
    start: float
    duration: float


class RenderPlan(BaseModel):
    scenes: list[Scene]
    transitions: list[Transition]
    title_events: list[TitleEvent]


def run(
    inputs: list[Path],
    output: Path,
    *,
    duration: float = 3600.0,
    seed: int | None = None,
    title_card: Path | None = None,
    width: int = 640,
    height: int = 360,
    fps: int = 10,
    still_duration: float = 30.0,
    start_black_duration: float = 8.0,
    default_still_fade: float = 4.0,
    title_probability: float = 0.05,
    title_duration: float = 8.0,
    title_fade: float = 4.0,
    overwrite: bool = False,
) -> None:
    config = RenderConfig(
        inputs=inputs,
        output=output,
        duration=duration,
        seed=seed,
        title_card=title_card,
        width=width,
        height=height,
        fps=fps,
        still_duration=still_duration,
        start_black_duration=start_black_duration,
        default_still_fade=default_still_fade,
        title_probability=title_probability,
        title_duration=title_duration,
        title_fade=title_fade,
        overwrite=overwrite,
    )
    render(config)


class RenderConfig(BaseModel):
    inputs: list[Path]
    output: Path
    duration: float = 3600.0
    seed: int | None = None
    title_card: Path | None = None
    width: int = 640
    height: int = 360
    fps: int = 10
    still_duration: float = 30.0
    start_black_duration: float = 8.0
    default_still_fade: float = 4.0
    title_probability: float = 0.05
    title_duration: float = 8.0
    title_fade: float = 4.0
    overwrite: bool = False


def render(config: RenderConfig) -> None:
    validate_config(config)
    media = [probe_media(path, config.still_duration) for path in config.inputs]
    plan = build_plan(config, media)
    command = ffmpeg_command(config, plan)
    sp.run(command, check=True)


def validate_config(config: RenderConfig) -> None:
    if not config.inputs:
        sys.exit("at least one input is required")
    if config.output.exists() and not config.overwrite:
        sys.exit(f"{config.output} already exists")
    if config.duration <= 0:
        sys.exit("duration must be positive")
    if config.width <= 0 or config.height <= 0 or config.fps <= 0:
        sys.exit("width, height, and fps must be positive")
    if config.still_duration <= 0:
        sys.exit("still_duration must be positive")
    if config.default_still_fade <= 0:
        sys.exit("default_still_fade must be positive")
    if not 0 <= config.title_probability <= 1:
        sys.exit("title_probability must be between 0 and 1")
    if config.title_duration <= 0 or config.title_fade < 0:
        sys.exit("title_duration must be positive and title_fade must not be negative")


def probe_media(path: Path, still_duration: float) -> Media:
    if not path.exists():
        sys.exit(f"{path} does not exist")
    is_still = path.suffix.lower() in IMAGE_SUFFIXES
    duration = still_duration if is_still else probe_duration(path)
    if duration <= 0:
        sys.exit(f"{path} has no positive duration")
    return Media(path=path, duration=duration, is_still=is_still)


def probe_duration(path: Path) -> float:
    result = sp.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            path.as_posix(),
        ],
        check=True,
        text=True,
        stdout=sp.PIPE,
    )
    return float(result.stdout.strip())


def build_plan(config: RenderConfig, media: list[Media]) -> RenderPlan:
    rng = random.Random(config.seed)
    scenes = [Scene(media=black_media(), duration=config.start_black_duration)]
    transitions: list[Transition] = []
    title_events: list[TitleEvent] = []

    if config.title_card is not None:
        title = Media(
            path=config.title_card, duration=config.title_duration, is_still=True
        )
        scenes.append(Scene(media=title, duration=config.title_duration))
        transitions.append(
            Transition(duration=_clamp_fade(config.title_fade, scenes[-2], scenes[-1]))
        )
        scenes.append(Scene(media=black_media(), duration=config.start_black_duration))
        transitions.append(
            Transition(duration=_clamp_fade(config.title_fade, scenes[-2], scenes[-1]))
        )

    current = scenes[-1]
    while timeline_duration(scenes, transitions) < config.duration:
        next_media = choose_media(rng, media, current.media)
        next_scene = Scene(media=next_media, duration=next_media.duration)
        transition = Transition(
            duration=fade_duration(
                current,
                next_scene,
                default_still_fade=config.default_still_fade,
            )
        )
        scenes.append(next_scene)
        transitions.append(transition)
        if config.title_card is not None and rng.random() < config.title_probability:
            title_events.append(
                TitleEvent(
                    start=max(
                        0.0,
                        timeline_duration(scenes, transitions)
                        - next_scene.duration / 2,
                    ),
                    duration=config.title_duration,
                )
            )
        current = next_scene

    return RenderPlan(scenes=scenes, transitions=transitions, title_events=title_events)


def choose_media(rng: random.Random, media: list[Media], current: Media) -> Media:
    choices = [m for m in media if m.path != current.path]
    return rng.choice(choices or media)


def fade_duration(
    current: Scene, next_scene: Scene, *, default_still_fade: float
) -> float:
    if current.media.is_still and next_scene.media.is_still:
        fade = default_still_fade
    elif current.media.is_still:
        fade = next_scene.duration / 2
    elif next_scene.media.is_still:
        fade = current.duration / 2
    else:
        fade = min(current.duration, next_scene.duration) / 2
    return _clamp_fade(fade, current, next_scene)


def _clamp_fade(fade: float, current: Scene, next_scene: Scene) -> float:
    limit = min(current.duration, next_scene.duration) / 2
    return max(0.0, min(fade, limit))


def timeline_duration(scenes: list[Scene], transitions: list[Transition]) -> float:
    return sum(s.duration for s in scenes) - sum(t.duration for t in transitions)


def black_media() -> Media:
    return Media(path=Path("__black__"), duration=float("inf"), is_still=True)


def ffmpeg_command(config: RenderConfig, plan: RenderPlan) -> list[str]:
    command = ["ffmpeg", "-hide_banner"]
    if config.overwrite:
        command.append("-y")
    else:
        command.append("-n")

    for scene in plan.scenes:
        command.extend(input_args(scene))

    for event in plan.title_events:
        if config.title_card is not None:
            command.extend(
                [
                    "-loop",
                    "1",
                    "-t",
                    f"{event.duration:.6f}",
                    "-i",
                    config.title_card.as_posix(),
                ]
            )

    filter_complex, output_label = filter_graph(config, plan)
    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            output_label,
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            config.output.as_posix(),
        ]
    )
    return command


def input_args(scene: Scene) -> list[str]:
    duration = f"{scene.duration:.6f}"
    if scene.media.path == Path("__black__"):
        return [
            "-f",
            "lavfi",
            "-t",
            duration,
            "-i",
            f"color=c=black:s=16x16:r=1:d={duration}",
        ]
    if scene.media.is_still:
        return ["-loop", "1", "-t", duration, "-i", scene.media.path.as_posix()]
    return ["-stream_loop", "-1", "-t", duration, "-i", scene.media.path.as_posix()]


def filter_graph(config: RenderConfig, plan: RenderPlan) -> tuple[str, str]:
    filters: list[str] = []
    for index, scene in enumerate(plan.scenes):
        filters.append(normalize_filter(index, scene, config))

    current_label = "v0"
    elapsed = plan.scenes[0].duration
    for index, transition in enumerate(plan.transitions, start=1):
        offset = max(0.0, elapsed - transition.duration)
        next_label = f"x{index}"
        filters.append(
            f"[{current_label}][v{index}]"
            f"xfade=transition=fade:duration={transition.duration:.6f}:"
            f"offset={offset:.6f}[{next_label}]"
        )
        current_label = next_label
        elapsed += plan.scenes[index].duration - transition.duration

    title_input = len(plan.scenes)
    for index, event in enumerate(plan.title_events):
        title_label = f"title{index}"
        filters.append(title_filter(config, title_input + index, event, title_label))
        next_label = f"overlay{index}"
        filters.append(
            f"[{current_label}][{title_label}]"
            f"overlay=(W-w)/2:(H-h)/2:eof_action=pass[{next_label}]"
        )
        current_label = next_label

    return ";".join(filters), f"[{current_label}]"


def normalize_filter(index: int, scene: Scene, config: RenderConfig) -> str:
    return (
        f"[{index}:v]"
        f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={config.fps},format=yuv420p,"
        f"trim=duration={scene.duration:.6f},setpts=PTS-STARTPTS[v{index}]"
    )


def title_filter(
    config: RenderConfig, input_index: int, event: TitleEvent, output_label: str
) -> str:
    fade_out_start = max(0.0, event.duration - config.title_fade)
    return (
        f"[{input_index}:v]"
        f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2,"
        "format=rgba,"
        f"fade=t=in:st=0:d={config.title_fade:.6f}:alpha=1,"
        f"fade=t=out:st={fade_out_start:.6f}:d={config.title_fade:.6f}:alpha=1,"
        f"setpts=PTS-STARTPTS+{event.start:.6f}/TB[{output_label}]"
    )


def main() -> None:
    tyro.cli(run)


if __name__ == "__main__":
    main()
