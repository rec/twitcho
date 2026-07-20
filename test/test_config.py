from pathlib import Path

import pytest
from pydantic import ValidationError

from twitcho.config import Twitcho


def test_channel_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="must be positive"):
        Twitcho(
            device_name="X18",
            channel=0,
            video=Path("visual-bed.mp4"),
            twitch_key="key",
        )


def test_twitcho_requires_stereo_pair_start_channel() -> None:
    config = Twitcho(
        device_name="X18",
        channel=17,
        video=Path("visual-bed.mp4"),
        twitch_key="key",
    )

    assert config.required_channels == 18
    assert config.rtmp_url == "rtmp://live.twitch.tv/app/key"
