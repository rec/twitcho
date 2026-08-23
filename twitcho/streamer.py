import random
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice
from reccy import process

from .config import Twitcho
from .control import ControlController, RuntimeState
from .programs import update_bitrate


@dataclass(frozen=True)
class VideoOverlay:
    name: str
    image: Path
    input_index: int
    gap_index: int
    interval: float
    duration: float
    fade: float


def stream(config: Twitcho, controller: ControlController) -> int:
    state = controller.state
    requested_stop = False
    result = 1
    ffmpeg = subprocess.Popen(
        ffmpeg_command(config),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    ffmpeg_output = process.capture_stderr(
        ffmpeg,
        lambda line: update_bitrate(state, line),
        thread_name="TwitchoProcessOutput",
    )
    try:
        state.set_ffmpeg(alive=True)
        state.set_state("streaming")
        with sounddevice.InputStream(
            callback=_audio_callback(config, ffmpeg, state),
            channels=config.required_channels,
            device=config.device_name,
            dtype="float32",
            samplerate=config.sample_rate,
        ):
            while ffmpeg.poll() is None:
                if should_stop(controller):
                    requested_stop = True
                    state.set_state("stopping")
                    process.terminate(ffmpeg)
                    break
                time.sleep(0.05)
            returncode = ffmpeg.wait()
            state.set_ffmpeg(alive=False, returncode=returncode)
            if returncode and not requested_stop:
                process.report_failed_process(ffmpeg_command(config), ffmpeg_output)
            result = 0 if requested_stop else returncode
    except KeyboardInterrupt:
        state.set_state("stopping")
        process.terminate(ffmpeg)
        result = 0
    except BrokenPipeError:
        state.set_error("ffmpeg input pipe closed")
        result = 1
    finally:
        if ffmpeg.stdin is not None:
            ffmpeg.stdin.close()
        process.terminate(ffmpeg)
        state.set_ffmpeg(alive=False, returncode=ffmpeg.returncode)
        if state.snapshot()["state"] != "failed":
            state.set_state("stopped")
    return result


def should_stop(controller: ControlController) -> bool:
    while not controller.commands.empty():
        command = controller.commands.get_nowait()
        if command.name == "stop":
            return True
    return False


def ffmpeg_command(config: Twitcho) -> list[str]:
    overlays: list[VideoOverlay] = []
    next_input = 2
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostats",
        "-progress",
        "pipe:2",
        "-f",
        "f32le",
        "-ar",
        str(config.sample_rate),
        "-ac",
        "2",
        "-i",
        "pipe:0",
        "-re",
        "-stream_loop",
        "-1",
        "-i",
        config.video.as_posix(),
    ]
    if config.title_card is not None:
        overlays.append(
            VideoOverlay(
                name="title",
                image=config.title_card,
                input_index=next_input,
                gap_index=next_input + 1,
                interval=config.title_interval,
                duration=config.title_duration,
                fade=config.title_fade,
            )
        )
        command.extend(overlay_input_args(config, overlays[-1]))
        next_input += 2
    if (image := random_image(config)) is not None:
        overlays.append(
            VideoOverlay(
                name="image",
                image=image,
                input_index=next_input,
                gap_index=next_input + 1,
                interval=config.image_interval,
                duration=config.image_duration,
                fade=config.image_fade,
            )
        )
        command.extend(overlay_input_args(config, overlays[-1]))
    if overlays:
        command.extend(
            ["-filter_complex", overlay_filter(config, overlays), "-map", "[video]"]
        )
    else:
        command.extend(["-map", "1:v:0"])
    command.extend(
        [
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "animation",
            "-b:v",
            config.video_bitrate,
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(config.video_frame_rate),
            "-s",
            config.video_resolution,
            "-c:a",
            "aac",
            "-b:a",
            config.audio_bitrate,
            "-ar",
            str(config.sample_rate),
            "-ac",
            "2",
            "-f",
            "flv",
            config.rtmp_url,
        ]
    )
    return command


def title_input_args(config: Twitcho) -> list[str]:
    assert config.title_card is not None
    return overlay_input_args(
        config,
        VideoOverlay(
            name="title",
            image=config.title_card,
            input_index=2,
            gap_index=3,
            interval=config.title_interval,
            duration=config.title_duration,
            fade=config.title_fade,
        ),
    )


def overlay_input_args(config: Twitcho, overlay: VideoOverlay) -> list[str]:
    gap_duration = overlay.interval - overlay.duration
    width, height = video_size(config)
    return [
        "-loop",
        "1",
        "-t",
        f"{overlay.duration:.6f}",
        "-i",
        overlay.image.as_posix(),
        "-f",
        "lavfi",
        "-t",
        f"{gap_duration:.6f}",
        "-i",
        (
            "color="
            f"c=black@0.0:s={width}x{height}:"
            f"r={config.video_frame_rate}:d={gap_duration:.6f}"
        ),
    ]


def title_filter(config: Twitcho) -> str:
    assert config.title_card is not None
    return overlay_filter(
        config,
        [
            VideoOverlay(
                name="title",
                image=config.title_card,
                input_index=2,
                gap_index=3,
                interval=config.title_interval,
                duration=config.title_duration,
                fade=config.title_fade,
            )
        ],
    )


def overlay_filter(config: Twitcho, overlays: list[VideoOverlay]) -> str:
    width, height = video_size(config)
    parts = [
        "[1:v]"
        f"scale={width}:{height},fps={config.video_frame_rate},"
        "format=yuv420p[base];"
    ]
    current = "base"
    for index, overlay in enumerate(overlays):
        output = "video" if index == len(overlays) - 1 else f"base{index + 1}"
        parts.append(overlay_video_filter(config, overlay))
        parts.append(
            f"[{current}][{overlay.name}_loop]"
            f"overlay=(W-w)/2:(H-h)/2:eof_action=repeat[{output}]"
        )
        current = output
    return "".join(parts)


def overlay_video_filter(config: Twitcho, overlay: VideoOverlay) -> str:
    width, height = video_size(config)
    fade_out_start = max(0.0, overlay.duration - overlay.fade)
    loop_frames = max(1, round(overlay.interval * config.video_frame_rate))
    return (
        f"[{overlay.input_index}:v]"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={config.video_frame_rate},format=rgba,"
        f"trim=duration={overlay.duration:.6f},"
        "setpts=PTS-STARTPTS,"
        f"fade=t=in:st=0:d={overlay.fade:.6f}:alpha=1,"
        f"fade=t=out:st={fade_out_start:.6f}:d={overlay.fade:.6f}:alpha=1"
        f"[{overlay.name}_visible];"
        f"[{overlay.gap_index}:v]format=rgba,setpts=PTS-STARTPTS[{overlay.name}_gap];"
        f"[{overlay.name}_visible][{overlay.name}_gap]concat=n=2:v=1:a=0,"
        f"loop=loop=-1:size={loop_frames}:start=0,"
        f"setpts=N/FRAME_RATE/TB[{overlay.name}_loop];"
    )


def random_image(config: Twitcho) -> Path | None:
    if config.image_interval <= 0 or config.image_chance <= 0:
        return None
    if random.random() >= config.image_chance:
        return None
    images = image_paths(config.image_dir)
    if not images:
        return None
    return random.choice(images)


def image_paths(image_dir: Path) -> list[Path]:
    if not image_dir.exists():
        return []
    return sorted(
        p
        for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def video_size(config: Twitcho) -> tuple[int, int]:
    width, height = config.video_resolution.lower().split("x", maxsplit=1)
    return int(width), int(height)


def select_stereo_pair(config: Twitcho, data: np.ndarray) -> np.ndarray:
    begin = config.channel - 1
    end = begin + 2
    if data.shape[1] < end:
        raise ValueError(
            f"device returned {data.shape[1]} channels; channel {config.channel} "
            "requires a stereo pair"
        )
    return np.ascontiguousarray(data[:, begin:end])


def _audio_callback(
    config: Twitcho, process: subprocess.Popen[bytes], state: RuntimeState
) -> Callable[[np.ndarray, int, object, object], None]:
    def callback(
        indata: np.ndarray,
        frames: int,
        time: object,
        status: object,
    ) -> None:
        if process.stdin is not None:
            stereo = select_stereo_pair(config, indata)
            if state.is_muted():
                stereo = np.zeros_like(stereo)
            state.record_audio(
                frames=frames,
                sample_rate=config.sample_rate,
                left_level_db=level_db(stereo[:, 0]),
                right_level_db=level_db(stereo[:, 1]),
                clipping=bool(np.max(np.abs(stereo)) >= 1.0),
            )
            process.stdin.write(stereo.tobytes())

    return callback


def level_db(samples: np.ndarray) -> float:
    peak = float(np.max(np.abs(samples)))
    if peak <= 0:
        return -120.0
    return float(20 * np.log10(peak))


IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
