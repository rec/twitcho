import io
from pathlib import Path

import numpy as np
import pytest

from twitcho.config import Twitcho
from twitcho.control import RuntimeState
from twitcho.streamer import _audio_callback, ffmpeg_command, select_stereo_pair


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
    assert command[-1] == "rtmp://live.twitch.tv/app/key"


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
