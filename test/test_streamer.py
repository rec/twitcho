import io
from pathlib import Path

import numpy as np
import pytest

from twitcho.config import Twitcho
from twitcho.control import RuntimeState
from twitcho.streamer import (
    _audio_callback,
    ffmpeg_command,
    select_stereo_pair,
    title_filter,
    video_size,
)


def _config() -> Twitcho:
    return Twitcho(
        device_name="X18",
        channel=2,
        video=Path("visual-bed.mp4"),
        twitch_key="key",
    )


def test_ffmpeg_command_streams_audio_pipe_and_video_loop() -> None:
    command = ffmpeg_command(_config())

    assert command[:10] == [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "f32le",
        "-ar",
        "48000",
        "-ac",
        "2",
    ]
    assert "visual-bed.mp4" in command
    assert "-stream_loop" in command
    assert "-filter_complex" not in command
    assert command[-1] == "rtmp://live.twitch.tv/app/key"


def test_ffmpeg_command_overlays_title_card(tmp_path: Path) -> None:
    title = tmp_path / "title.png"
    title.touch()
    config = _config().model_copy(update={"title_card": title})

    command = ffmpeg_command(config)
    graph = command[command.index("-filter_complex") + 1]

    assert title.as_posix() in command
    assert "color=c=black@0.0:s=640x360:r=10:d=172.000000" in command
    assert command[command.index("-map") + 1] == "[video]"
    assert "[base][title_loop]overlay=(W-w)/2:(H-h)/2" in graph
    assert "fade=t=in:st=0:d=2.000000:alpha=1" in graph
    assert "fade=t=out:st=6.000000:d=2.000000:alpha=1" in graph
    assert "loop=loop=-1:size=1800:start=0" in graph


def test_video_size_parses_resolution() -> None:
    assert video_size(_config()) == (640, 360)


def test_title_filter_uses_configured_timing(tmp_path: Path) -> None:
    title = tmp_path / "title.png"
    title.touch()
    config = _config().model_copy(
        update={
            "title_card": title,
            "title_interval": 60,
            "title_duration": 10,
            "title_fade": 3,
            "video_frame_rate": 24,
            "video_resolution": "1280x720",
        }
    )

    graph = title_filter(config)

    assert "scale=1280:720" in graph
    assert "fps=24" in graph
    assert "fade=t=out:st=7.000000:d=3.000000:alpha=1" in graph
    assert "loop=loop=-1:size=1440:start=0" in graph


def test_select_stereo_pair_uses_one_based_channel_number() -> None:
    config = _config()
    data = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.float32)

    assert select_stereo_pair(config, data).tolist() == [[2, 3], [6, 7]]


def test_select_stereo_pair_rejects_missing_second_channel() -> None:
    with pytest.raises(ValueError, match="requires a stereo pair"):
        select_stereo_pair(_config(), np.zeros((2, 2), dtype=np.float32))


def test_audio_callback_writes_silence_when_muted() -> None:
    state = RuntimeState()
    state.set_muted(True)
    process = FakeProcess()
    callback = _audio_callback(_config(), process, state)

    callback(np.array([[1, -1, 0], [0.5, -0.5, 0]], dtype=np.float32), 2, None, None)

    written = np.frombuffer(process.stdin.getvalue(), dtype=np.float32).reshape((2, 2))
    assert written.tolist() == [[0, 0], [0, 0]]
    assert state.snapshot()["audio_frames"] == 2


class FakeProcess:
    def __init__(self) -> None:
        self.stdin = io.BytesIO()
