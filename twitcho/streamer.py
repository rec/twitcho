import subprocess as sp
import tempfile
import typing as t
from math import isinf
from pathlib import Path

import numpy as np
import sounddevice
from pydantic import BaseModel

from .config import AnimationSegment, Twitcho


class ClipPart(BaseModel):
    animation: Path
    begin: float
    end: float


def stream(config: Twitcho) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".ffconcat") as concat_file:
        concat_file.write(animation_playlist(config))
        concat_file.flush()

        process = sp.Popen(
            ffmpeg_command(config, Path(concat_file.name)),
            stdin=sp.PIPE,
        )
        try:
            with sounddevice.InputStream(
                callback=_audio_callback(config, process),
                channels=config.required_channels,
                device=config.device_name,
                dtype="float32",
                samplerate=config.sample_rate,
            ):
                process.wait()
        except KeyboardInterrupt:
            process.terminate()
        finally:
            if process.stdin is not None:
                process.stdin.close()
            if process.poll() is None:
                process.terminate()
                process.wait()


def ffmpeg_command(config: Twitcho, concat_file: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
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
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_file.as_posix(),
        "-map",
        "1:v:0",
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


def animation_playlist(config: Twitcho) -> str:
    lines = ["ffconcat version 1.0"]
    for segment in config.segments.values():
        for part in clip_parts(segment):
            lines.extend(
                [
                    f"file {_concat_quote(part.animation)}",
                    f"inpoint {part.begin:.6f}",
                ]
            )
            if not isinf(part.end):
                lines.append(f"outpoint {part.end:.6f}")
    return "\n".join(lines) + "\n"


def clip_parts(segment: AnimationSegment) -> list[ClipPart]:
    result: list[ClipPart] = []
    if segment.body.begin < segment.loop.begin:
        result.append(
            ClipPart(
                animation=segment.animation,
                begin=segment.body.begin,
                end=segment.loop.begin,
            )
        )

    for _ in range(segment.loop_count):
        if segment.loop.begin < segment.loop.end:
            result.append(
                ClipPart(
                    animation=segment.animation,
                    begin=segment.loop.begin,
                    end=segment.loop.end,
                )
            )

    if segment.loop.end < segment.body.end:
        result.append(
            ClipPart(
                animation=segment.animation,
                begin=segment.loop.end,
                end=segment.body.end,
            )
        )
    return result


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
    config: Twitcho, process: sp.Popen[bytes]
) -> t.Callable[[np.ndarray, int, object, object], None]:
    def callback(
        indata: np.ndarray,
        frames: int,
        time: object,
        status: object,
    ) -> None:
        if process.stdin is not None:
            process.stdin.write(select_stereo_pair(config, indata).tobytes())

    return callback


def _concat_quote(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "'\\''") + "'"
