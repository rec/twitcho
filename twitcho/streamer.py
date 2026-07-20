import subprocess as sp
import typing as t

import numpy as np
import sounddevice

from .config import Twitcho


def stream(config: Twitcho) -> None:
    process = sp.Popen(
        ffmpeg_command(config),
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


def ffmpeg_command(config: Twitcho) -> list[str]:
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
        "-i",
        config.video.as_posix(),
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
