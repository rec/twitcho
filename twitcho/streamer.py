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
from .programs import capture_process_stderr, report_failed_process
from .twitch_api import TwitchApi


def stream(config: Twitcho) -> None:
    state = RuntimeState()
    controller = ControlController(state=state, twitch=TwitchApi.from_config(config))
    server = thread = None
    if config.control_enabled:
        server, thread = start_control_server(config, controller)

    requested_stop = False
    process = sp.Popen(
        ffmpeg_command(config),
        stdin=sp.PIPE,
        stdout=sp.DEVNULL,
        stderr=sp.PIPE,
    )
    ffmpeg_output = capture_process_stderr(process, state)
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
                    requested_stop = True
                    state.set_state("stopping")
                    process.terminate()
                    break
                time.sleep(0.05)
            returncode = process.wait()
            state.set_ffmpeg(alive=False, returncode=returncode)
            if returncode and not requested_stop:
                report_failed_process(ffmpeg_command(config), ffmpeg_output)
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
        command.extend(title_input_args(config))
        command.extend(["-filter_complex", title_filter(config), "-map", "[video]"])
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
    gap_duration = config.title_interval - config.title_duration
    width, height = video_size(config)
    return [
        "-loop",
        "1",
        "-t",
        f"{config.title_duration:.6f}",
        "-i",
        config.title_card.as_posix(),
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
    width, height = video_size(config)
    fade_out_start = max(0.0, config.title_duration - config.title_fade)
    loop_frames = max(1, round(config.title_interval * config.video_frame_rate))
    return (
        "[1:v]"
        f"scale={width}:{height},fps={config.video_frame_rate},"
        "format=yuv420p[base];"
        "[2:v]"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={config.video_frame_rate},format=rgba,"
        f"trim=duration={config.title_duration:.6f},"
        "setpts=PTS-STARTPTS,"
        f"fade=t=in:st=0:d={config.title_fade:.6f}:alpha=1,"
        f"fade=t=out:st={fade_out_start:.6f}:d={config.title_fade:.6f}:alpha=1"
        "[title_visible];"
        "[3:v]format=rgba,setpts=PTS-STARTPTS[title_gap];"
        "[title_visible][title_gap]concat=n=2:v=1:a=0,"
        f"loop=loop=-1:size={loop_frames}:start=0,"
        "setpts=N/FRAME_RATE/TB[title_loop];"
        "[base][title_loop]overlay=(W-w)/2:(H-h)/2:eof_action=repeat[video]"
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
