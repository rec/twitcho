from pathlib import Path

import numpy as np
import pytest

from twitcho.config import Twitcho
from twitcho.streamer import ffmpeg_command, select_stereo_pair


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
