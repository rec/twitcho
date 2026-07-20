from pathlib import Path

import pytest
from pydantic import ValidationError

from twitcho.config import AnimationSegment, Range, Twitcho


def test_range_end_must_not_be_before_begin() -> None:
    with pytest.raises(ValidationError, match="range end"):
        Range(begin=2, end=1)


def test_animation_loop_must_be_inside_body() -> None:
    with pytest.raises(ValidationError, match="loop end"):
        AnimationSegment(
            animation=Path("idle.mp4"),
            body=Range(begin=0, end=10),
            loop=Range(begin=2, end=12),
        )


def test_twitcho_requires_stereo_pair_start_channel() -> None:
    config = Twitcho(
        device_name="X18",
        channel=17,
        segments={"idle": AnimationSegment(animation=Path("idle.mp4"))},
        twitch_key="key",
    )

    assert config.required_channels == 18
    assert config.rtmp_url == "rtmp://live.twitch.tv/app/key"
