from pathlib import Path

import numpy as np
import pytest

from twitcho.config import AnimationSegment, Range, Twitcho
from twitcho.streamer import (
    animation_playlist,
    clip_parts,
    ffmpeg_command,
    select_stereo_pair,
)


def _config() -> Twitcho:
    return Twitcho(
        device_name="X18",
        channel=2,
        segments={
            "idle": AnimationSegment(
                animation=Path("idle.mp4"),
                body=Range(begin=1, end=9),
                loop=Range(begin=3, end=7),
                loop_count=2,
            )
        },
        twitch_key="key",
    )


def test_clip_parts_include_intro_loops_and_outro() -> None:
    segment = _config().segments["idle"]

    assert [p.model_dump() for p in clip_parts(segment)] == [
        {"animation": Path("idle.mp4"), "begin": 1.0, "end": 3.0},
        {"animation": Path("idle.mp4"), "begin": 3.0, "end": 7.0},
        {"animation": Path("idle.mp4"), "begin": 3.0, "end": 7.0},
        {"animation": Path("idle.mp4"), "begin": 7.0, "end": 9.0},
    ]


def test_animation_playlist_uses_concat_demuxer_format() -> None:
    assert animation_playlist(_config()) == (
        "ffconcat version 1.0\n"
        "file 'idle.mp4'\n"
        "inpoint 1.000000\n"
        "outpoint 3.000000\n"
        "file 'idle.mp4'\n"
        "inpoint 3.000000\n"
        "outpoint 7.000000\n"
        "file 'idle.mp4'\n"
        "inpoint 3.000000\n"
        "outpoint 7.000000\n"
        "file 'idle.mp4'\n"
        "inpoint 7.000000\n"
        "outpoint 9.000000\n"
    )


def test_ffmpeg_command_streams_audio_pipe_and_animation_playlist() -> None:
    command = ffmpeg_command(_config(), Path("animations.ffconcat"))

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
    assert "animations.ffconcat" in command
    assert command[-1] == "rtmp://live.twitch.tv/app/key"


def test_select_stereo_pair_uses_one_based_channel_number() -> None:
    config = _config()
    data = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.float32)

    assert select_stereo_pair(config, data).tolist() == [[2, 3], [6, 7]]


def test_select_stereo_pair_rejects_missing_second_channel() -> None:
    with pytest.raises(ValueError, match="requires a stereo pair"):
        select_stereo_pair(_config(), np.zeros((2, 2), dtype=np.float32))
