import subprocess as sp
import time
import typing as t

import numpy as np
import sounddevice

from .config import Twitcho
from .control import (
    ControlController,
    RuntimeState,
    start_control_server,
    stop_control_server,
)


def stream(config: Twitcho) -> None:
    state = RuntimeState()
    controller = ControlController(state=state)
    server = thread = None
    if config.control_enabled:
        server, thread = start_control_server(config, controller)

    process = sp.Popen(
        ffmpeg_command(config),
        stdin=sp.PIPE,
    )
    try:
        state.set_ffmpeg(alive=True)
        state.set_state("streaming")
        if server is not None:
            server.broadcast({"type": "status", "status": state.snapshot()})
        with sounddevice.InputStream(
            callback=_audio_callback(config, process, state),
            channels=config.required_channels,
            device=config.device_name,
            dtype="float32",
            samplerate=config.sample_rate,
        ):
            while process.poll() is None:
                if should_stop(controller):
                    state.set_state("stopping")
                    process.terminate()
                    break
                time.sleep(0.05)
            state.set_ffmpeg(alive=False, returncode=process.wait())
    except KeyboardInterrupt:
        state.set_state("stopping")
        process.terminate()
    except BrokenPipeError:
        state.set_error("ffmpeg input pipe closed")
    finally:
        if process.stdin is not None:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
            process.wait()
        state.set_ffmpeg(alive=False, returncode=process.returncode)
        if state.snapshot()["state"] != "failed":
            state.set_state("stopped")
        if server is not None:
            server.broadcast({"type": "status", "status": state.snapshot()})
        stop_control_server(server, thread)


def should_stop(controller: ControlController) -> bool:
    while not controller.commands.empty():
        command = controller.commands.get_nowait()
        if command.name == "stop":
            return True
    return False


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
    config: Twitcho, process: sp.Popen[bytes], state: RuntimeState
) -> t.Callable[[np.ndarray, int, object, object], None]:
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
